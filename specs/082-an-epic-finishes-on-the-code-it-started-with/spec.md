---
state: draft
# HOLD LIFTED 2026-08-22: the condition was "after our next pypi deployment"
# and ergane-cli 0.2.0 shipped that morning (tag v0.2.0 at e5f9ce6). Draft
# still — the ready flip stays the operator's call after he reads the refined
# set.
#
# REFINED 2026-08-22 (operator session, tree at e5f9ce6). What the pass did:
#   - RE-ANCHORED THE WHOLE SET. Sixteen commits landed since the draft's
#     158aa63; EpicWorkflow's defn had moved 72 lines, the heartbeat
#     derivation 25, and 086 rewrote the very interceptor the plan cites
#     (its `return` is now load-bearing — see the plan's worker.py notes).
#     All plan and spec-body line citations now resolve against e5f9ce6.
#   - FR-009 IS ALREADY LANDED CODE. The adapter's R4 machinery (pid_file +
#     _reap, factory/workgraph/adapter.py:732/:1320, tested in
#     tests/test_adapter.py) records and reaps predecessor process groups in
#     the runtime sidecar. US5 shrinks to the heartbeat cap; FR-009 and
#     US5-S4 are reworded as reuse-and-verify. Plan trap 10 rewritten.
#   - TWO NEW TRAPS (plan 13 rewritten, 14 added): tests/test_worker.py runs
#     against the TIME-SKIPPING server whose deployment-API support is
#     unproven — probe before leaning on it; and D-050 (constitution 2.5.0,
#     landed after this draft) charges pasted evidence to the 64 KiB diff
#     budget, which this evidence-heavy spec must respect — paste minimal
#     proving lines, never transcripts.
#   - LIVE PROBES RE-RUN, all unchanged: server 1.31.2 answers the
#     deployment API, SDK 1.31.0 carries the full surface. Both motivating
#     findings still open in the ledger.
#
# The original hold note, kept for the record:
# "i dont want to actually work on this until after our next pypi deployment."
#
# Drafted 2026-08-21 ~4:15 PM CT by an operator session, at the operator's
# instruction, tree at 158aa63 (ergane-buildout).
#
# WHAT THIS IS, IN THE OPERATOR'S OWN WORDS. "the worker consistently needs to
# be restarted ... its a pain in the ass to deal with. can we do anything like
# having a rolling strategy for workers ...? anything where it would be draining
# off of one worker while the next worker is already taking new work." And, on
# the follow-up: retire the unversioned unit, and stop paying hours of wall
# clock waiting for a heartbeat timeout to notice a dead worker.
#
# THE MEASUREMENT, verified line by line at draft time:
#   - One worker process serves everything: `factory/worker.py:1-6` says it
#     plainly, `factory/workgraph/workflow.py:259` pins the one queue
#     (`workgraph`), and the generated unit runs from the operator's live
#     checkout (`factory/supervision/units.py:309` `WorkingDirectory=
#     {layout.install_root}`; `resolve_layout` at `:165` derives install_root
#     as the directory holding `factory/`).
#   - A worker restart cancels every in-flight attempt — `factory/worker.py:37-43`
#     documents the cancellation path as the *feature*. The standing operator
#     rule ("restart only when nothing is in flight") exists because the floor
#     rarely offers that window.
#   - When the worker dies instead of draining, the attempt's activity sits
#     PENDING until a heartbeat timeout derived as HALF THE ATTEMPT DEADLINE:
#     `factory/workgraph/workflow.py:404-409` `_agent_heartbeat_timeout` =
#     max(timeout_s/2, five beats). On 2026-08-19 that parked an epic ~2h
#     behind a killed worker; the runbook fix was `temporal activity fail` by
#     hand. The derivation's own comment (`:386-400`) argues "detecting a dead
#     worker a minute later costs nothing (the epic is stalled either way)" —
#     the 08-19 wedge priced that argument.
#
# LIVE PROBES RUN AT DRAFT TIME (2026-08-21, not read from docs):
#   - `temporal --version` → CLI 1.8.2, Server 1.31.2, UI 2.50.1.
#   - `temporal worker deployment list --namespace factory` against the RUNNING
#     dev server → an empty table, not an error. The deployment-versioning API
#     is live on this host today; no dynamic-config flag was needed.
#   - temporalio SDK 1.31.0 (probed by import): `Worker(deployment_config=...)`
#     exists; `WorkerDeploymentConfig(version, use_worker_versioning,
#     default_versioning_behavior)`; `@workflow.defn(versioning_behavior=...)`;
#     `temporalio.common` carries `VersioningBehavior`,
#     `WorkerDeploymentVersion`, `PinnedVersioningOverride`,
#     `AutoUpgradeVersioningOverride`.
#   - CLI verbs confirmed by `temporal worker deployment --help`: `list`,
#     `describe`, `describe-version`, `set-current-version`, `delete-version`,
#     `set-ramping-version` (deliberately unused here).
---

# Feature Specification: an epic finishes on the code it started with

## The gap, stated precisely

The factory has exactly one worker process, and that process is the deployment:
it polls the one `workgraph` queue, imports factory code from the operator's
live checkout, and is restarted in place every time factory code changes. Three
costs follow, each already paid at least once:

- **New code reaches epics only through a restart, and a restart kills every
  in-flight attempt.** The cancellation path is well built
  (`factory/worker.py:37-43` — the agent's process group is terminated, the
  transcript archived, the attempt classified KILLED) — but well-built
  cancellation is still hours of agent work re-bought at dispatch prices. The
  operating rule this forces, "restart only when nothing is in flight," asks
  for a window a busy floor rarely opens.
- **The checkout the worker imported and the checkout on disk drift apart**
  the moment an operator edits anything, which is why "never modify factory
  code while an attempt is in flight" is a standing rule and why 053 built a
  revision query just to detect the skew.
- **A worker that dies instead of draining parks its epic for hours.** The
  attempt's liveness bound is derived as half its deadline
  (`factory/workgraph/workflow.py:429-434`), so a multi-hour attempt whose
  worker crashed sits PENDING for a multi-hour heartbeat timeout while the
  scheduler waits behind it. 2026-08-19: ~2h, cleared by hand with
  `temporal activity fail`.

Consumer deployments feel almost none of this — a wheel install is static code,
and restarts are rare there by construction. This is operator tooling for the
factory that builds itself; it is also the substrate the parked `ergane update`
verb (upgrade in place without eating running epics) will stand on.

## The rule this spec is asking for

**An epic finishes on the code it started with, and new code takes the floor
without killing anyone's work.** Deploying factory code means starting a new
versioned worker beside the old one; the old worker drains — it keeps serving
exactly the epics pinned to it and takes nothing new — and is reaped when the
last of them closes. Nothing is restarted in place, ever, and the operator's
checkout stops being executable surface.

## What this spec does not change

- **The task queue.** One queue, `workgraph`
  (`factory/workgraph/workflow.py:259`). Versions are routed by the server;
  no per-version queues, no queue renames.
- **The other units.** The bridge, the probe and the managed Temporal server
  stay unversioned and restart freely — none of them holds epic state.
- **Attempt deadlines and retries.** `start_to_close_timeout` and
  `_AGENT_RETRIES` stay exactly as they are. Only the *liveness* bound moves
  (US5), and only its ceiling.
- **Ramping.** `set-ramping-version` exists and stays unused. A factory with
  one operator does not need percentage rollouts; current-version-or-drained
  is the whole model.
- **Wheel installs.** Static by design. `worker deploy` refuses there by name
  (FR-004); it does not grow a wheel story.

## User Scenarios & Testing

### User Story 1 - The worker declares which code it is (Priority: P1)

As the operator, when a worker starts it registers itself as a version of the
`ergane-worker` deployment — build id = the git revision it already captures
for 053's revision query — and the workflows it serves are pinned to the
version that started them.

**Why this priority**: P1 and the spine. Every other story routes work by the
version registration this one creates.

**Independent Test**: boot a worker with versioning engaged against a real dev
server and read the registered version back; boot one without and observe
today's behavior unchanged.

**Acceptance Scenarios**:

1. **Given** versioning engaged (the environment names it — see FR-001's
   gating), **When** the worker boots, **Then** it registers deployment
   `ergane-worker` with its captured revision as build id, and
   `temporal worker deployment describe` shows it — proven by a committed test
   against a real dev server (the harness `tests/test_worker.py` already runs
   the production registration against one).
2. **Given** versioning not engaged, **When** the worker boots, **Then**
   registration, polling and behavior are today's, bit for bit — proven by a
   committed test. **This is the control**: landing this story must change
   nothing on a floor that has not deployed with US2 yet. A versioned worker
   polls only its version's tasks; a floor whose only worker went versioned
   before a current version existed would stall every new epic.
3. **Given** a current version set, **When** an epic starts, **Then** it runs
   pinned — every workflow task and activity of that epic is served by that
   version's worker even after a newer version becomes current — proven by
   committed test where the harness allows and by pasted live evidence where
   it does not (SC-001).
4. **Given** the roadmap running, **When** a newer version becomes current,
   **Then** the roadmap adopts it at a run boundary and the old version still
   drains to zero — the roadmap must never be the workflow that keeps a dead
   version alive (FR-002). The adoption mechanism is the plan's choice; the
   drain is the proof.
5. **Given** a worker whose revision capture returns None (a wheel, an
   unpacked tree), **When** versioning is engaged, **Then** it refuses to
   start by name rather than registering an unknowable build id — proven by a
   committed test.

---

### User Story 2 - A deploy puts new code on the floor without touching the old (Priority: P1)

As the operator, `ergane worker deploy` takes a committed revision, gives it a
frozen checkout and its own environment, starts it as a versioned worker unit
beside whatever is running, and makes it current — while every in-flight
attempt keeps running on the version it started with.

**Why this priority**: P1. This is the verb the operator asked for, in the
shape he asked for it: "draining off of one worker while the next worker is
already taking new work."

**Independent Test**: with an attempt in flight on version A, deploy version B;
the attempt finishes on A, the next epic reports B.

**Acceptance Scenarios**:

1. **Given** an attempt in flight, **When** the operator deploys a new
   revision, **Then** the attempt continues undisturbed to completion on the
   old version — no cancellation, no KILLED classification, no
   `temporal activity fail` — proven by pasted live evidence (SC-001,
   SC-005).
2. **Given** a deploy has completed, **When** the next epic starts, **Then**
   its 053 revision query reports the deployed build id — proven by pasted
   live evidence.
3. **Given** the same revision deployed twice, **When** the second deploy
   runs, **Then** it converges without error — unit already running, version
   already current, nothing duplicated — proven by a committed test.
4. **Given** a tree that is not a git checkout, a revision that does not
   resolve to a commit, or uncommitted changes with no explicit revision
   named, **When** deploy is asked, **Then** it refuses by name before
   touching systemd or Temporal — proven by committed tests. A deploy ships
   *commits*; there is no sha for a dirty tree to be accountable to.
5. **Given** the new worker fails to register within the wait bound, **When**
   deploy times out, **Then** it reports the degraded state and leaves the
   unit running rather than rolling back — a re-run converges (scenario 3) —
   proven by a committed test.
6. **Given** a completed deploy, **When** the operator reads its report,
   **Then** it names every version of the deployment and each one's state
   (current / draining / drained) — proven by a committed test of the
   rendering.

---

### User Story 3 - A drained version leaves the host (Priority: P2)

As the operator, when the last epic pinned to an old version closes, that
version's worker unit stops, its frozen checkout is removed, and its version
record is deleted — without me remembering to do any of it.

**Why this priority**: P2. Without reaping, "a trio of workers" becomes a
graveyard of workers, each holding a venv and a checkout on disk forever.

**Independent Test**: drive a version to drained on a dev server, run the
sweep, observe unit gone, checkout gone, version record gone.

**Acceptance Scenarios**:

1. **Given** a non-current version whose drainage is complete, **When** the
   sweep next runs, **Then** its unit is stopped and disabled, its checkout
   removed (through git's own worktree removal, never a bare `rm`), and its
   version record deleted — proven by pasted live evidence (SC-003).
2. **Given** the current version, idle or not, **When** the sweep runs,
   **Then** it is never touched — proven by a committed test. **The
   control.**
3. **Given** a non-current version with any open pinned workflow, **When**
   the sweep runs, **Then** it is left alone — proven by a committed test.
   The reap decision MUST be a pure function of (versions, drainage, open
   work, units) so both controls are cheap to prove.

---

### User Story 4 - The unversioned unit retires (Priority: P2)

As the operator, `ergane worker install` no longer writes the in-place-restart
worker unit at all: it writes the versioned template, and migration off the
legacy unit is refused while any epic that predates versioning is still open.

**Why this priority**: P2, and the operator's explicit instruction: "retire the
unversioned unit." Two deployment stories is how skew comes back.

**Independent Test**: install on a clean host and observe only the template;
uninstall on a host with the legacy unit and observe it removed; attempt
migration with a pre-versioning epic open and observe the named refusal.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** units are generated, **Then**
   `ergane-worker@.service` (template) is written and `ergane-worker.service`
   is not — proven by a committed test of the generated set.
2. **Given** a host still running the legacy unit, **When** the operator
   migrates, **Then** the legacy unit is removed only after no epic started
   before versioning remains open; while one is, the removal is refused by
   name — proven by a committed test of the decision and pasted live evidence
   of the happy path (SC-004).
3. **Given** `ergane worker uninstall`, **When** it runs on a host with
   versioned instances and a legacy unit, **Then** it removes exactly what
   install wrote — template, instances, and the legacy unit if its text
   matches what install once wrote — preserving today's provenance rules —
   proven by a committed test.

---

### User Story 5 - A dead worker is noticed in beats, not hours (Priority: P2)

As the operator, when a worker crashes mid-attempt, the factory notices in
minutes bounded by a constant — never by a bound derived from how long the
attempt was allowed to run.

**Why this priority**: P2. Rolling deploys (US1-US3) eliminate the *planned*
restart entirely; after they land, the heartbeat timeout prices exactly one
thing — crashes — and today it prices them at up to half an attempt deadline.

**Independent Test**: SIGKILL the worker unit mid-attempt; measure schedule of
the replacement attempt against the wall clock.

**Acceptance Scenarios**:

1. **Given** an attempt with a multi-hour deadline, **When** its heartbeat
   timeout is derived, **Then** the result is capped at a small constant
   (minutes, not a fraction of the deadline) — proven by a committed test
   naming the cap.
2. **Given** an attempt whose deadline is short, **When** the timeout is
   derived, **Then** today's floor (five beats) still holds — proven by a
   committed test. **The control**: short attempts must not collapse below
   the beat that bounds them.
3. **Given** a worker killed uncleanly mid-attempt, **When** the timeout
   fires, **Then** the replacement attempt is scheduled within minutes — on
   2026-08-19 this took ~2 hours — proven by pasted live evidence with
   timestamps (SC-002).
4. **Given** a false positive — the server misses beats past the cap while
   the agent actually lives — **When** the retry dispatches into the same
   worktree, **Then** the recorded predecessor process group is terminated
   before the new attempt starts, so two agents never share a worktree, and
   **Given** no recorded predecessor, **Then** nothing is killed — the
   control. **The 2026-08-22 refinement found this machinery already landed
   and tested** (the adapter's R4: `pid_file`/`_reap`,
   `factory/workgraph/adapter.py:732`, `:1320`, exercised by
   `tests/test_adapter.py`) — the story verifies the existing coverage holds
   under the new cap and extends it only if a genuine gap is proven.

### Edge Cases

- Two deploys racing: the verb takes a lock; the loser reports the winner.
- The current version's worker crashes: systemd restarts the same instance —
  same frozen checkout, same build id — a restart re-registers, it never
  mints a version. `Restart=on-failure` semantics carry over to the template.
- A deploy from a revision older than the current version: allowed (it is how
  a rollback is spelled), reported loudly as such.
- Disk growth: bounded by the reaper; the deploy report names every version
  still on disk so an operator sees a stuck drain as a list that will not
  shrink.
- The reaper and a racing dispatch: drained state is re-checked against open
  workflows immediately before deletion, not remembered from the sweep's
  start.

## Requirements

### Functional Requirements

- **FR-001**: The worker MUST register as a version of deployment
  `ergane-worker` — build id = its captured revision — with pinned behavior
  for `EpicWorkflow`, `EscalationWorkflow` and `QuestionWorkflow`. Versioning
  MUST be engaged by explicit environment, and a worker without it MUST
  behave exactly as today, so this lands dark and US2 turns it on.
- **FR-002**: The roadmap MUST end up executing on a newly-current version
  without manual surgery, and an old version MUST drain to zero while the
  roadmap lives on. Whether that is auto-upgrade behavior, a versioning
  override applied at deploy, or an explicit continue-as-new nudge is the
  plan's decision — proven by the drain, not asserted.
- **FR-003**: `ergane worker deploy <revision>` MUST create a frozen checkout
  of that commit outside the operator's checkout, give it its own dependency
  environment, start it as an instance of the versioned unit template, wait
  bounded for registration, and set it current. Re-running MUST converge.
- **FR-004**: Deploy MUST refuse by name: a tree that is not a git checkout;
  a revision that is not a commit; a dirty tree when no explicit revision was
  named; an unreachable systemd session or Temporal server.
- **FR-005**: A version that is not current, has completed draining, and has
  no open pinned workflow MUST be reaped — unit stopped and disabled, frozen
  checkout removed via git worktree removal, version record deleted. The
  current version MUST never be reaped. The decision MUST be a pure,
  separately tested function.
- **FR-006**: `ergane worker install` MUST write the versioned template and
  MUST NOT write the legacy `ergane-worker.service`; `uninstall` MUST remove
  the legacy unit under the same match-what-install-wrote provenance rule it
  applies to everything else.
- **FR-007**: Migration MUST NOT strand an epic started before versioning:
  removing the legacy unit is refused by name while any such epic is open.
- **FR-008**: The attempt heartbeat timeout MUST be independent of the
  attempt deadline above a constant cap on the order of minutes, and the cap
  MUST be at least twenty beats so a transient blip is survivable. The
  five-beat floor stays. Gate heartbeats stay as they are — theirs is already
  bounded by the per-gate deadline, not the suite's.
- **FR-009**: Before starting an agent, the attempt activity MUST terminate a
  recorded live predecessor process group for the same node, and MUST record
  its own where the next attempt will find it — beside the attempt's other
  sidecar evidence, never inside the diffed tree. **Refinement 2026-08-22:
  this requirement is already satisfied by landed code** — the adapter's R4
  machinery records `.factory/run/<epic>/<node>.pid` and reaps before every
  launch. The story MUST reuse that machinery, not build a parallel one;
  its obligation shrinks to verifying the existing tests still prove the
  scenario under the US5 cap.
- **FR-010**: The deploy report MUST name every version of the deployment and
  its state, so "what is on the floor right now" is one command's output.

### Key Entities

- **Deployment version**: `ergane-worker` + build id (short revision); the
  server-side identity work is routed by.
- **Frozen checkout**: the on-disk git worktree + dependency environment a
  version executes from; created by deploy, removed by the reaper.
- **Unit instance**: `ergane-worker@<build-id>.service`; one per live
  version.
- **Drainage**: the server's own statement that a version has no open pinned
  work; the reaper's precondition, re-checked at the moment of action.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-003, FR-004, FR-010]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-005]
  persona: opus-closer
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006, FR-007]
  persona: opus-closer
US5:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009]
  persona: opus-closer
```

The chain through US2 is logic (deploy needs registration; reaping and
retiring need deploy). US5's edge to US1 is contention, not logic — both
stories edit `factory/workgraph/workflow.py` and `factory/worker.py`, and US5
needs US1's lines to have stopped moving. US3 and US4 both build on US2 but
touch disjoint surfaces (reaper vs. unit generation) — with one caveat the
plan names at T016: US2 lands the template-instance plumbing in `units.py`
that US4's generation swap then completes; US4's `depends_on_merged: [US2]`
exists for that shared file as much as for the logic.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A deploy executed while an attempt is in flight completes with:
  the attempt finishing normally on its version (no KILLED classification),
  and the next epic's revision query reporting the new build id. Pasted live
  evidence.
- **SC-002**: A worker SIGKILLed mid-attempt yields a replacement attempt
  scheduled within 3 minutes of the kill, wall clock, against the 2026-08-19
  baseline of ~2 hours. Pasted live evidence with timestamps.
- **SC-003**: Within one sweep interval of the last pinned epic closing, the
  old version's unit is inactive, its checkout gone, and
  `temporal worker deployment describe-version` no longer knows it. Pasted
  live evidence.
- **SC-004**: After migration, `systemctl --user list-units 'ergane-worker*'`
  shows template instances only; the legacy unit file is gone from the unit
  directory.
- **SC-005**: Zero manual `temporal activity fail` invocations across a
  deploy performed mid-flight — the 08-19 runbook line dies.

## Assumptions

- The dev server on this host (1.31.2) answers the worker-deployment API
  today — probed at draft time, empty table not an error. The plan re-probes
  before implementation rather than trusting this frontmatter.
- Deploys come from committed revisions reachable in the operator checkout;
  the operator host has `git` and `uv` (already true for the factory to run
  at all).
- One deployment name (`ergane-worker`) per namespace; multi-repo identity
  stays where 040 put it — in workflow ids and search attributes, not in
  deployment names.
- The bridge, probe and managed-Temporal units hold no epic state and stay
  unversioned; a bridge restart during a deploy loses nothing durable.
- Ramping stays unused; current-or-draining is the whole lifecycle.
