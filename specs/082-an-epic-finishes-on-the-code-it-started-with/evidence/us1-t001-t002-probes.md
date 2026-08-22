# US1 T001/T002 — the two probes the plan told us to run before writing code

Run 2026-08-22 against the session dev server (`localhost:7233`, Server 1.31.2,
temporalio 1.31.0), in namespace `default` and under deployment names prefixed
`probe-082-` so nothing touches the `factory` namespace or the `ergane-worker`
deployment. Toy workflows only; two `Worker`s on one queue with different build
ids stand in for two deployments. Only the decisive lines are pasted (D-050:
evidence is charged to the 64 KiB diff budget).

## T001 — a PINNED workflow's continue-as-new inherits its version

Toy workflow declared `versioning_behavior=PINNED`, started while `probe-v1`
was current, then `probe-v2` made current, then signalled to continue-as-new:

```
[set-current] probe-082-can.probe-v1
[run1 under v1-current]              run_id=01a02ae5 behavior=PINNED deployment_version=probe-082-can.probe-v1
[set-current] probe-082-can.probe-v2
[run1 after v2 became current]       run_id=01a02ae5 behavior=PINNED deployment_version=probe-082-can.probe-v1
[run2 (after continue-as-new)]       run_id=82d55f9a behavior=PINNED deployment_version=probe-082-can.probe-v1
```

**Answer: it inherits.** A new run id, still on `probe-v1` with `probe-v2`
current. This is trap 5's bad case, measured: a PINNED `RoadmapWorkflow` would
carry its version across every continue-as-new and keep a dead version alive
forever, and FR-002 would fail structurally.

## T001b — AUTO_UPGRADE adopts at the next workflow task, and the old version drains

Same shape, toy workflow declared `AUTO_UPGRADE`:

```
[set-current] probe-082-au.probe-v1
[run1 under v1-current]                        run_id=01a02ae5 behavior=AUTO_UPGRADE deployment_version=probe-082-au.probe-v1
[set-current] probe-082-au.probe-v2
[run1 immediately after v2 became current]     run_id=01a02ae5 behavior=AUTO_UPGRADE deployment_version=probe-082-au.probe-v1
[run1 after a workflow task on v2-current]     run_id=d6426b07 behavior=AUTO_UPGRADE deployment_version=probe-082-au.probe-v2
```

Adoption is at the next workflow task, not at process restart. And the version
it left drained to zero on its own, polled to completion:

```
t+0s   status=VERSION_DRAINAGE_STATUS_DRAINING
t+165s status=VERSION_DRAINAGE_STATUS_DRAINED
```

**This transcript is what chooses `RoadmapWorkflow`'s behavior**: `AUTO_UPGRADE`
for the roadmap (US1-S4/FR-002), `PINNED` for epic, escalation and question
(US1-S3/FR-001). No override, no continue-as-new nudge, no manual surgery — the
roadmap's own run boundaries already come often enough, and the drain above is
the proof rather than the assertion.

## T002 part A — the control finding: an unversioned worker CANNOT serve a defn that declares a behavior

The same toy workflow declared two ways, both handed to a worker with **no**
`deployment_config` (today's worker):

```
--- Part A: unversioned worker, defn declaring PINNED ---
WARN temporalio_sdk_core::worker::workflow: Error while completing workflow activation
  error=code: 'Client specified an invalid argument',
  message: "versioning behavior cannot be specified without deployment options being set with versioned mode"
VERDICT A: STALLED — an unversioned worker CANNOT run a PINNED defn
[part A final] status=1 history_len=8 behavior=UNSPECIFIED version='.'

--- Part A control: unversioned worker, today's defn ---
result: 2
VERDICT A-control: SERVED — today's defn on today's worker, unchanged
```

The workflow task never completes; the server rejects the completion and the
task retries forever. **So the environment gate must cover the decorator
argument too, not just `deployment_config`.** Decorating the four defns
unconditionally would break every workflow on every floor that has not deployed
US2 yet — the exact failure US1-S2 exists to forbid. The gate is therefore one
decision read once at import (`factory/versioning.py`), consumed by both
`build_worker` and the four `@workflow.defn` decorators, and `UNSPECIFIED` is
the disengaged value because the SDK treats it as absent
(`_workflow_instance.py:2474` tests the field for truthiness, and
`VersioningBehavior.UNSPECIFIED` is 0).

## T002 part B — a pre-versioning run is served by the versioned current worker

A run started mid-flight by today's worker (defn with no behavior), then the
worker replaced by a versioned one that becomes current:

```
[pre-versioning run, mid-flight]              status=1 history_len=5 behavior=UNSPECIFIED version='.'
[phase1] today's worker shut down
[phase2] set-current probe-082-mig2.mig-v1
[pre-versioning run right after set-current]  status=1 history_len=5 behavior=UNSPECIFIED version='.'
result: 2
VERDICT B: SERVED — the pre-versioning run completed on the new version
[part B final] status=2 history_len=10 behavior=PINNED version='probe-082-mig2.mig-v1'
```

**Answer: served, and auto-upgraded onto the current version at its next
workflow task**, where it then pins. An open epic started before versioning is
not stranded by a versioned worker becoming current — but it is adopted onto
whatever version is current at that moment, which is the fact US4's migration
refusal (FR-007) has to encode: the danger is not a stalled pre-versioning
epic, it is a pre-versioning epic silently pinning to a version that is not the
code it started with.
