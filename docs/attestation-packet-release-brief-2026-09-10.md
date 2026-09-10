# Story and spec audit packets — release brief

Draft, 2026-09-10. Inspected against buildout
`a654fca272c34d017888f6dc9281b4654be8f469`.

The user requested downloadable attestation packets and prefers waiting for 0.6
if the addition is reasonably bounded. The recommendation is to include the
packet feature, not the entire general-purpose lifecycle-listener framework.
The provisional estimate is 10–14 additional story-sized changes and roughly
3–5 additional days including qualification, beyond the remaining migration and
release work. This is not a measured throughput forecast or publication date;
refinement may change it. This brief is neither a ready trio nor a dispatch.

## Problem Statement

An operator cannot currently download one attributable account of how a story
was built and verified. Tokens, verification results, ladder history, files,
landing checks and team-owned evidence are distributed across stores and CI.
Answering an audit question means reconstructing that history, sometimes after
the worktree or workflow history has expired.

A spec can span multiple epic executions, so collecting only the latest
successful attempt also hides retries, failed runs and their cost. A green final
verdict does not show whether the judge ran, what it objected to, or whether a
later check actually established that each objection was resolved.

## Solution

Produce a versioned audit packet automatically for each terminal story/node and
each terminal epic, plus a spec-revision rollup that identifies the epic
executions and story packets it incorporates. A packet is an exportable archive
containing a human-readable report, a structured manifest and declared evidence
attachments. Include failed and killed outcomes, not only successful landings.

Teams declare which artifacts they want carried and can attach later CI, UAT,
security, quality or SBOM evidence through a bounded local/CI interface. The
default is a private local packet with a CLI export path. A team's existing CI
can upload that exported archive to its authorized artifact storage; no new web
service or automatic public upload is required for the first release.

The requested “hook” is a bounded, retryable packet-generation integration at
the factory's lifecycle boundary, with an attachment/export interface for CI.
It is not arbitrary code loaded into workflow execution. Evidence collection
happens before worktree cleanup; landing and later CI facts enrich subsequent
packet revisions. The judge stays in the inner loop, never in CI.

## User Stories

1. As an operator, I want one downloadable story packet so I can review its
   build without searching several stores.
2. As an operator, I want a spec packet that identifies every included story
   revision and epic execution so reruns cannot silently replace prior history.
3. As an auditor, I want all attempts, including failed, killed, timed-out and
   pre-agent launches, so unsuccessful work and spend are not concealed.
4. As an auditor, I want the frozen ladder configuration and the actual ordered
   attempts, personas, runners, routes and model identities so declared routing
   is distinguishable from observed execution.
5. As an operator, I want input, output and supported cache/reasoning token
   dimensions, separated by builder and judge, with source and completeness so
   I can compare costs without adding overlapping counters.
6. As an auditor, I want every retained judge evaluation, scenario result,
   feedback and retry so the final PASS does not erase earlier objections.
7. As an auditor, I want a resolution map that cites later verification or an
   explicit disposition so “fully fixed” is a bounded evidence claim.
8. As an operator, I want unavailable, skipped, contradictory and incomplete
   judge evidence visible so an unjudged PASS is not presented as judge approval.
9. As an auditor, I want gate commands, statuses, timings and captured reports
   so the packet describes tests actually run, not tests merely present.
10. As an auditor, I want base, attempted, verified and landed revisions plus
    added, modified, renamed and deleted paths so I know what each result covers.
11. As a team, I want to declare coverage, scans, SBOMs and opaque artifacts so
    Ergane carries the evidence formats our existing tools produce.
12. As a team, I want to attach integration/UAT and CI reports later with their
    producer, tested revision and run identity so post-build evidence remains
    attributable and does not overwrite the original packet.
13. As an operator, I want missing, invalid, oversized or refused attachments
    named so an archive cannot look complete merely because collection failed.
14. As an operator, I want generation to survive activity retries and worker
    restart without duplicate packets or changed node outcomes.
15. As an auditor, I want to verify archive contents against its manifest and
    digests without a running factory, while understanding that checksums alone
    do not authenticate the producer or certify software quality.
16. As a team, I want private-by-default storage, explicit export selection and
    retention policy so feedback and proprietary reports are not published with
    a public PR by accident.

## Implementation Decisions

These are proposed module boundaries for refinement, not authorization to change
the live worker, policy or storage destination.

### Evidence identity and acquisition

Reuse the persisted verification and usage surfaces, current-attempt evidence
work in spec160, and declared artifact carriage in draft134. Do not build a
parallel gate runner, ledger, judge or artifact collector.

Persist an identity envelope while the facts are available: target identity,
spec revision/fingerprint, epic workflow and execution identity, node, attempt,
phase/form and relevant judge-evaluation identity. Ordinal attempt numbers alone
are not unique across epic executions. Capture the frozen ladder, runner and
route rather than looking up today's persona registry at export time.

Distinguish the dispatched model alias from the actually serving model and
fallbacks when supported telemetry identifies them. Unknown serving identity is
unknown, not a claim that the configured first model handled every request.

Verification already persists dispatch, builder persona/alias/route, gate
results, criteria identity, judge findings and model alias. It does not by itself
retain every requested fact. The legacy usage row lacks a matching dispatch
dimension, and some historical “confirmed” rows lack token measurements.
Reconcile the narrow usage-correctness work in draft135; never join ambiguous
old rows by node and attempt number and pretend attribution is exact. Audit
judge retries too: retaining the final judge result is not proof that earlier
judge calls and their usage were retained.

For new executions, complete identity/capture is a release acceptance condition.
For historical imports, preserve missing or ambiguous dimensions with reasons;
do not backfill models, usage or feedback from current settings.

### Packet assembly and export

Use a pure report/manifest assembler over explicit records, with a separate
bounded storage/export boundary. Include per-attempt records and total known
usage with missing-source counts. A complete total is unavailable if required
contributors are unknown. Do not add CLI corroboration to gateway counts, add
overlapping cached/reasoning counts twice, or treat subscription dollars as zero.

Keep raw judge outcomes, composed verification results, gate contradictions and
operator dispositions distinct. Map a finding to later evidence for the same
scenario and criteria fingerprint; changed criteria, absent judgment or unrelated
green CI cannot establish that the old objection was fixed. Narrative feedback
without an attributable resolution remains open/unverified. Do not spend another
LLM call to infer that everything was fixed.

Record the exact revisions for attempted, verified and landed file manifests;
include binary changes, renames and deletions. Landing CI can test a speculative
merge rather than the original attempt, so retain its tested revision and run
identity separately. A link alone is not durable report retention: where report
bytes are requested, capture them or mark them unavailable/expired.

The archive has a schema version, stable record identity, content digests and a
readable summary. Repeated export of identical evidence is reproducible. Verify
it offline. Preserve original packet revisions; new attachments create a new
revision linked to its predecessor rather than modifying old evidence in place.

### Lifecycle generation and spec rollup

Use activities for acquisition, persistence and finalization. Workflow replay
must not write files or invoke hooks; activity retries still require stable
idempotency keys. Collect worktree evidence before cleanup and finalize status
from the recorded terminal outcome. Missing evidence is visible, never silently
omitted to make finalization succeed.

Packet generation failure has a bounded retry policy and visible failed/pending
status. It neither consumes a coding rung nor changes a recorded build outcome.
Teams requiring a complete packet can enforce that as an explicit existing CI or
release gate. Installing a listener must not quietly become a new build decider.

The spec rollup names its selected spec revision and all contributing epic
executions. Story content and spend are separate aggregations: show the selected
landed story revision once, preserve all attributable attempts and costs once.
An epic reaching COMPLETED does not by itself mean every node landed. Failed,
killed, pending, baseline-attested and observed-landed coverage stay distinct.

### Team artifact and CI attachment interface

Reuse draft134's declared artifact types, adding descriptive purpose/producer
metadata as needed rather than requiring one scanner. Let a team specify desired
evidence, size/retention limits and optional completeness expectations. Carry
bytes and provenance without interpreting an SBOM or asserting a scan's accuracy.

The CI interface accepts a local artifact plus explicit target, spec/node/run,
tested revision, producer, result/status and content digest. Refuse an identity
or revision mismatch; do not infer the subject from the checkout's current HEAD.
Record the submitter and claimed producer separately. A submitted report is not
automatically authenticated producer evidence. No arbitrary URL fetching is
needed in the first implementation.

Filesystem boundaries reject traversal, escaping symlinks, unsafe archive names,
unexpected special files, oversized inputs and silent overwrite. Render feedback
as untrusted text; do not execute attachments or embed active report content in
the human-readable summary. Export no credentials, raw private rollouts, node
homes or private absolute paths. Opaque attachments need explicit team selection
and visibility controls; pattern redaction cannot certify arbitrary bytes as safe
to publish. Preserve the existing public PR body's narrow evidence policy.

## Testing Decisions

Test every module through its public behavior, with temporary stores/artifacts
and a relocated runtime root. No new dependency is assumed. Existing evidence
round-trip, archive, gate worktree-watch, usage aggregation and Temporal workflow
tests supply controls; focused regressions run before a full suite.

Release qualification must include:

- A failed first attempt followed by a different configured rung and successful
  landing; its packet must show both attempts, actual routes/models and usage.
- Two epic executions with the same node and attempt ordinal; no overwritten
  history, ambiguous join or duplicate spend after record/finalizer redelivery.
- Multiple judge calls, scenario feedback and later resolution, plus unavailable
  judge, contradictory findings, changed criteria and unresolved-feedback cases.
- Partial/unknown token sources, gateway plus CLI corroboration, builder plus
  judge usage and subscription cost controls.
- Real declared gate artifact collection before actual cleanup, including
  ignored paths, absent artifacts and an undeclared additional worktree write.
- Retry and worker-restart recovery, delayed finalization and terminal failed/
  killed nodes; packet behavior must not change ladder or landing decisions.
- A two-story spec rollup spanning a partial earlier epic and a later remainder,
  retaining failed work while selecting each landed story only once.
- CI/UAT attachment after landing, exact revision matching, repeat submission,
  immutable previous packet, corruption detection and offline export verification.
- Sensitive content, path/symlink escape, binary/oversized files and untrusted
  HTML/report controls. Test export visibility independently from gate success.
- An isolated end-to-end build producing a downloadable packet through the
  actual supported deployment, followed by independent inspection of its
  contents against factory and CI records. Synthetic green tests alone are not
  proof that live evidence survives deployment handover and cleanup.

## Out of Scope

- The full draft124 factory/harness event registry, per-turn telemetry fan-out,
  arbitrary in-process plugins or a new inbound webhook server.
- A new dashboard, hosted artifact service or vendor-specific scanner suite.
- Automatic public uploads, account/repository creation, changed credentials,
  target visibility or client trust grants.
- Sending attachments to the judge; that is the separate draft144 question.
- Cryptographic signing identities, external notarization, compliance
  certification or a guarantee that passing checks prove software defect-free.
- Fabricated historical reconstruction or retroactive claims of complete audit
  coverage where the original evidence was never recorded.

## Further Notes

Tentative additional work: draft134's five artifact-carriage stories, up to three
usage-correctness stories from draft135, and roughly six new packet slices:
identity/acquisition, attempt report/resolution, archive/export, lifecycle
generation, spec rollup, and team CI attachment/qualification. Spec160 is already
in the approved migration work and is not counted again. Re-slice before dispatch
if any implementation plus its evidence would exceed the 64 KiB diff ceiling.

The final split may need more or fewer slices once judge-call retention and
cross-execution usage identity are fully traced. That is the largest uncertainty
in the estimate. Do not quietly remove token, feedback, ladder or attachment
requirements to fit a smaller estimate.

This is an audit packet, distinct from the glossary's **attested landing**, which
is a frontmatter-based reconciliation fact. Packet generation does not mark a
spec landed, close findings or attest that an unobserved story was built.

Next refinement must produce complete trios with explicit merge dependencies,
current symbol-anchored reuse claims, test-first tasks and a normal validation
report. The global roadmap remains paused; the active157 migration run is not
interrupted by this draft. This brief changes no release artifact or public repo.
