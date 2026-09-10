# Implementation Plan: each story and spec keeps an audit packet

Refined 2026-09-10 against buildout `60943a0ce3cb618ff6cfb19fd0d2df7b85ce6466`,
including the landed PR487 accounting interfaces.
Spec134 artifact carriage and spec160 current-attempt usage are planned
dependencies, not APIs claimed to exist at this revision. Re-read their landed
interfaces and revalidate this trio before dispatch. Spec135 is coordinated
release work with a separate spend-decision hold, not an excuse to trust a legacy
confirmation flag in a packet. The user approved the complete packet feature in
0.6; do not shrink it to a link list to meet an estimate.

## Current mechanisms inspected

- `factory/usage/models.py:72` — `KeyLease` and `factory/usage/models.py:131` — `UsageRecord`: no dispatch/invocation dimension; persona separates builder and judge but not repeated executions.
- `factory/activities/usage_activities.py:238` — `key_alias_for`: four-part alias; the ledger upserts on it. Merely adding dispatch to a packet cannot recover an overwritten usage row.
- `factory/activities/usage_activities.py:252` — `issue_attempt_key`: gateway, subscription and legacy direct branches; metadata and key recovery belong here, not in the report assembler.
- `factory/activities/usage_activities.py:474` — `teardown_attempt` and `factory/activities/usage_activities.py:581` — `_record_for`: final usage acquisition and ledger write; preserve key revocation on all paths.
- `factory/usage/ledger.py:427` — `_coverage`: read-only measured subtotals, missing/partial/legacy row coverage, sources and cost bases; these summaries do not establish invocation identity or completeness of optional metrics.
- `factory/usage/runner.py:147` — `archive_execution_usage` and `factory/usage/runner.py:193` — `read_attempt_usage`: existing subscription archive acquisition, including cancellation. Spec160 replaces Codex's evidence source with its current typed contract; preserve the independent Claude behavior.
- `factory/workgraph/workflow.py:578` — `EpicInput`: frozen execution configuration; packet policy must arrive through normal entry points, not be read from the host environment during replay.
- `factory/workgraph/workflow.py:1794` — `EpicWorkflow._run_node`: launches, questions and attempt charging; a launch identity is not a ladder slot.
- `factory/workgraph/workflow.py:2658` — `EpicWorkflow._verify`: phase verification persistence. Earlier failures can reach teardown without a verification result.
- `factory/workgraph/workflow.py:2811` — `EpicWorkflow._judge`: one key brackets all re-asks of one scoring job and only the last verdict is returned.
- `factory/workgraph/workflow.py:3004` — `EpicWorkflow._score` and `factory/activities/verify_activities.py:430` — `run_judge`: observable activity/transport boundaries; capture calls here without adding an LLM call or changing re-ask policy.
- `factory/verify/models.py:868` — `VerificationResult`: dispatch, base, criteria, composed result, gates and final judge evidence already exist; do not replace these authorities.
- `factory/verify/store.py:1238` — `_judge_to_dict`: serialization of the retained verdict is not retention of every earlier verdict.
- `factory/workgraph/workflow.py:3595` — `EpicWorkflow._poll_landing`: removes the worktree before recording MERGED. A terminal-only collector would arrive too late.
- `factory/workgraph/workflow.py:3687` — `EpicWorkflow._remove_worktree`: cleanup boundary also serves non-merged terminal paths.
- `factory/mergequeue/models.py:134` — `Landing` and `factory/mergequeue/models.py:181` — `PrSnapshot`: landing observations are distinct from branch CI and must name tested revisions.

## Owning modules and contracts

### US1 — Acquisition journal and execution attribution

Add a small `factory/attestation/` package for typed evidence identity and a
durable journal with explicit public read/write operations. This is an index and
snapshot of source evidence, not a new billing ledger. The journal persists
outside node worktrees under the existing resolved runtime root. Local SQLite
and the standard library suffice; use the existing single-host storage topology.

Freeze target identity from the graph/declaration (never infer it from cwd),
spec revision and fingerprint, workflow ID/run ID and immutable invocation ID.
Keep the ladder ordinal, launch ordinal, scoring-job ID, scoring-call ordinal and
activity delivery identity separate. Generate logical IDs in deterministic
workflow state, retain them across activity retries and distinguish new question
resumptions even when they spend no ladder slot. Record pre-issuance launch intent
and its failure; an absent lease is not a reason to lose the launch.

Extend the existing usage identity path additively for new dispatches, including
key alias/metadata and teardown, so two distinct invocations cannot upsert over
one another. Preserve old payload defaults and legacy readable rows. One scoring
job retains one key across re-asks. Never put the key/token itself in a packet.
Do not infer the run from an alias suffix, timestamps or current registry.

Capture builder runner/route and frozen ordered model aliases separately from
observed provider/model request metadata. For the HTTP judge, identify its
backend as the actual scoring transport, not a nonexistent CLI runner. Copy
available authoritative request IDs/model/usage while available; missing source
telemetry is explicit. Spec160 corroboration is consumed through its landed
typed contract, not by rescanning raw CLI rollouts.

Reuse `UsageRecord.usage_source`, `usage_status` and `cost_basis` from PR487;
extend the existing provenance vocabulary rather than introduce synonymous
fields. Its additive schema-v3 defaults leave historical rows explicitly legacy.
Preserve read-only access to schema-v2 stores without migration, and test both
legacy payload defaults and populated old rows. New invocation attribution must
not assign a guessed dispatch to those rows or rewrite historical measurements.

Represent completeness per metric/source. A new aggregate marked complete has
complete token totals but may still have unknown cache or request counts; legacy
confirmed rows can also contain missing token fields. Neither `usage_status`
nor `final_usage_confirmed` certifies every packet dimension. Include observed-source
coverage and unknown-contributor counts. Gateway ledger remains authoritative
for money; retain raw legacy monetary evidence with its source and uncertainty,
never rewrite historical zero/nonzero values in this story. CLI token evidence
can be separately reported when the gateway has none, but is not relabeled as
gateway-confirmed. Cache/reasoning dimensions that are subsets are not added to
their parents. Retain total known spend separately from a complete total.

### US2 — Judge history and pure report assembly

Capture each actual scoring result before the re-ask loop replaces it, and
persist unavailable/parse/transport failures with bounded sanitized evidence.
Where an activity or transport retries a network request, distinguish an actual
delivery from an idempotent persistence retry. Do not pretend exactly-once model
execution: a lost response can leave a charged request with unknown response.
The existing scoring job's total is authoritative once; allocate per-call usage
only with supported request-level attribution, never divide a total by calls.

The pure assembler accepts explicit journal/verification/usage/artifact records
and returns report data, with no live I/O or LLM. A resolution record names the
original scenario/fingerprint, later revision/evaluation and status:
verified-fixed, explicitly-dispositioned, unresolved or unverified. Changed
criteria are not a fix. Preserve gate contradictions beside raw judge and
composed outcomes. Only show fully-fixed when every relevant objection has
same-criterion later verification and no missing necessary evidence; this is a
bounded statement about those checks, not proof of defect-free code.

Read base/attempted/verified Git object IDs inside acquisition activities while
available; record a NUL-safe path/status manifest, binary/rename/deletion facts
and distinct snapshots when salvage creates a new commit. Report tests actually
executed and captured output completeness. Coverage exists only if a real report
was collected; a large test count is not a percentage.

### US3 — Immutable packet storage and offline CLI

Define schema-v1 ZIP with `manifest.json`, `report.md` and a deterministic
attachment namespace. Canonical JSON ordering, sorted names, fixed ZIP metadata
and a content-derived revision make repeated exports byte-identical. No export
timestamp or absolute source path may perturb that identity. Manifest records
the format/generator version, subject, evidence completeness, prior revision
and digests of report/attachment bytes; use a non-self-referential digest scheme.

Add one `ergane attestation` noun. Initial commands: `show` selects an explicit
subject and revision; `export --output ...` writes a local archive;
`verify <archive>` validates without a running factory or extracting files.
Finalize/attach/spec-selection options arrive in their owning stories. An
ambiguous subject is an error, never an implicit latest checkout. Use normal
CLI JSON and exit-code conventions, including explicit strict completeness.

Storage defaults: preserve evidence, directories0700/files0600, no network,
finite named byte/entry/text limits. Refuse existing unrelated output rather
than clobbering. Use staged writes plus atomic revision publication; a failed
write cannot advertise a complete packet. Identical revision publication is
idempotent. Runtime-root relocation affects storage paths, not portable identity.

Consume 134's collected references rather than re-read removed worktrees.
Recheck file type, containment, size and content digest on opened handles; lexical
validation alone cannot defeat symlink substitution or a hardlink to unrelated
data. Refuse unsafe aliases/special files; do not wait on FIFO reads. Offline
verification bounds both compressed and expanded bytes, rejects duplicate and
unlisted entries, and never extracts or executes content. Escape active markup
and redact text before rendering. Raw sessions/homes never enter the selection
set. Opaque bytes are explicitly selected and sensitivity-labeled; do not claim
a string-pattern scrub can certify arbitrary reports safe for publication.

### US4 — Bounded lifecycle finalization

Declare packet policy in the existing target manifest and thread it through the
CLI and roadmap dispatch paths into the frozen epic input. A minimal enabled
policy creates metadata packets automatically; absence on old configurations
preserves legacy behavior and says disabled. Validate positive finite limits;
do not silently read current config during an existing execution.

Use version-compatible Temporal command changes. Acquisition occurs before
ephemeral sources disappear; finalization follows usage teardown and terminal
outcome. Cover all cleanup routes, including failed/killed paths not passing
through landing. Register new activities with the actual worker; a helper with
no lifecycle caller does not satisfy this story. Return bounded references and
status in activity payloads, never attachment bytes or an unbounded history.

Persist pending intent before publication. Activity retry uses a stable evidence
set/revision key; a bounded failure leaves a visible failed/pending record and
allows the existing cleanup/outcome to proceed. `attestation finalize` retries
from retained evidence and cannot rerun coding, judge or landing. Missing
pre-cleanup evidence is an explicit irrecoverable gap, not fabricated recovery.
An epic packet lists every node, including unstarted/blocked ones. Status reads
are read-only: viewing a missing packet cannot implicitly generate one.

### US5 — Spec-revision rollup

Add a pure selection/aggregation layer. Pin explicit target and spec revision;
name all included epic executions and record exclusions/selection policy. Keep
two separate sets: selected content per story, and all attributable invocations
for usage history. Deduplicate by stable source identity, never model/amount or
node ordinal. Retain old attempts after amended-story selection. Baseline
attestations have no invented code/run evidence. A missing packet propagates a
gap, and unknown totals stay unknown. Export nested packet bytes with digests so
the downloadable archive is independently usable rather than only local links.

### US6 — Team policy and CI attachment

Extend the same noun with `attach`, using a local file and explicit target,
subject/revision, tested commit, CI run/delivery ID, producer, submitter and
claimed status. The tested commit must match the named subject snapshot or a
recorded authorized branch/merge-group/landed relationship; never accept an
arbitrary commit merely because it exists in Git. Producer claims are not
authenticated identity. No arbitrary URL fetch or inbound hook server.

Store accepted attachment events transactionally. Duplicate ID+digest is a
no-op; changed bytes under one ID refuse; concurrent different submissions both
survive and generate linked successor revisions. Refreshing a spec rollup is an
explicit new revision. Never edit old archive bytes in place.

Team policy names desired categories and completeness expectations, not scanner
commands that the workflow executes. Retention default is preserve; configured
expiry must leave unavailable/tombstone provenance and obey active reference
ownership. No blanket cleanup of a shared runtime root. Provide executable CLI
and CI examples to export a selected artifact to the team's existing private
CI artifact store. Upload is the team's configured CI step, never implicit in
packet generation and never a change to this repository's release workflow.

## Traps carried into every slice

1. **An attempt ordinal is not an invocation.** Question resumes and redispatch
   can reuse it; fixing only the export key leaves the usage writer overwriting.
2. **The final judge result is not the judge history.** Capture before re-ask;
   one scoring job's key total is not one identical total per re-ask.
3. **Observed file is not proven producer execution.** A carried artifact may
   predate its gate. Preserve 134 capture provenance and do not label an
   unchanged preexisting report freshly produced without evidence.
4. **Terminal cleanup already happened.** Collect early, finalize late; retry
   finalization cannot recover bytes nobody retained.
5. **Green is multidimensional.** Gates, raw judge, composed PASS, branch CI and
   merge-group CI differ; preserve each and its revision.
6. **A confirmed row need not have complete token fields.** Test dimensions and
   source coverage, not just the flag; unknown is not zero.
7. **Read intent is not repair intent.** Show/export/verify must not silently
   migrate a live ledger, regenerate packets or close findings.
8. **Activity retry is not exactly-once execution.** Journal idempotency and
   crash windows must be proven with real persistence, not mock call counts.
9. **A digest is not a signature.** Do not advertise certification or verified
   producer identity without a separate authenticated mechanism.

## Sizing, testing and release qualification

Six merge-ordered stories, each targeting at most about40KiB code+tests and
8KiB committed evidence, with margin below64KiB. US1 and US4 are the highest
risk for size; split under new story IDs before dispatch if the implementation
plan exceeds that bound. Never truncate required evidence just to pass sizing.
Use public behavior tests with temporary roots, source differences and controlled
peers; do not mutate live stores, accounts, user profiles or the current worker.

Run focused usage/verification/judge/archive/CLI/workflow regressions before the
declared full gate. Commit compact actual test output per story, not a narrative
claim. Temporal replay and restart tests need a real test workflow/store; CLI
examples need the actual parser and output, not source-string presence checks.

Release acceptance additionally requires an independently inspected deployed
end-to-end build: first attempt fails, another configured rung succeeds, all
judge calls/usage survive cleanup, native landing is identified, a team report
attaches later, and a spec packet exports and verifies offline after restart.
Use the already approved gateway route/deployment; this does not authorize new
subscription-account/pilot use. Compare archive contents to actual factory and
forge evidence. Missing expected gateway builder/judge usage is a release
qualification gap to repair, not permission to claim a complete packet because
the schema accepts unknown. Historical absent data stays honestly incomplete.
