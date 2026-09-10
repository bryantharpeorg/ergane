---
state: draft
depends_on_landed:
  - 134-a-gate-declares-the-artifact-it-writes-and-the-platform-carries-it
  - 160-each-codex-attempt-owns-its-evidence
---

# Feature Specification: each story and spec keeps an audit packet

## Provenance and release boundary

The user explicitly approved this feature for **0.6.0** on 2026-09-10 and
requested updated specs. This trio turns the release brief into six bounded
factory slices. Approval of release scope is not a claim of implementation,
readiness, dispatch, qualification, signing, or permission to publish private data.
The global roadmap remains paused; use the normal deliberate factory sequence.

An audit packet is not the glossary's **attested landing**. It records evidence;
it cannot mark a spec landed, decide a verdict, answer an escalation, or close a
finding. The judge remains in the inner loop, not in CI.

## Problem Statement

An operator cannot download one durable account of how a story was built:
tokens, ladder transitions, builder identities, judge feedback, gates, changed
files, landing checks and team reports live on separate surfaces. Keeping only
the final successful verification hides failed attempts, earlier judge calls and
their cost. A spec can span several epic executions with repeated node/attempt
ordinals. An archive assembled after cleanup can lose the evidence it promises.

## Solution and implementation boundaries

Automatically generate a private, versioned packet for terminal nodes and epics,
and a spec-revision rollup over their retained execution history. Each export
contains a readable report, machine-readable manifest and selected evidence
attachments. Teams choose their desired reports and can append CI, integration,
UAT, security, quality, coverage and SBOM evidence after landing. The bounded
lifecycle integration and CI attachment/export interface are the requested hook;
the generic listener registry in draft124 is not a dependency.

Reuse 134 for declared gate-artifact carriage and 160 for current Codex evidence.
135 remains a release companion for legacy usage correctness, not a prerequisite
API for this packet: the packet must assess measurement completeness itself,
even for a legacy row whose confirmation flag is wrong. This does not authorize
135's separately held spend-contract reversal or rewrite old ledger values.

The acquisition journal, pure report assembler and bounded archive boundary are
separate modules. They use existing stores and supported source contracts, not a
parallel gate runner, judge, usage counter or hosted service. No new dependency,
credential, target, scanner subscription or storage account is introduced.

## User Scenarios & Testing

### User Story 1 - Every execution keeps its identity and measured usage (Priority: P1)

As an auditor, I can distinguish every builder launch and scoring job, including
retries that use the same ladder ordinal, without reconstructing today's config.

**Independent Test**: Drive real issuance/teardown and persistence boundaries
against isolated fake-provider stores; compare independently retained rows.

**Acceptance Scenarios**:

1. **Given** two epic executions of the same spec/node/attempt and two question-resume launches sharing one ordinal, **When** their actual issuance and teardown paths run, **Then** committed tests prove distinct invocation and usage identities, preserved earlier records, and no duplicate spend on redelivery of one invocation.
2. **Given** a frozen ladder with different personas, runners, routes and model aliases, **When** an ordinary launch fails and a configured higher rung launches, **Then** the persisted evidence records the original ladder, ordered actual invocations, reason for transition and resolved selections; changing the registry before reading changes none of those facts, as proven by tests.
3. **Given** pre-agent refusal, failed issuance, timeout, cancellation and a question without a charged ladder slot, **When** each execution ends, **Then** a committed test proves an attributable launch/outcome record survives even without verification or usage; unknown counts are not zero and the packet path neither spends a rung nor issues an extra model request.
4. **Given** gateway usage plus Codex corroboration, subscription usage, partial metrics and an ambiguously attributable legacy row, **When** evidence is persisted and read, **Then** tests prove source-specific counts/completeness, unavailable subscription dollars, no gateway/CLI double count, and no guessed legacy join; configured aliases and observed serving-model identities remain separate.
5. **Given** a record with a request count but missing token fields, **When** token totals are projected, **Then** a committed test proves the legacy confirmed flag cannot make those missing dimensions complete, a known subtotal is labeled partial, and the complete total remains unavailable.

### User Story 2 - Judge feedback and what resolved it survive every re-ask (Priority: P1)

As an auditor, I can see who judged each attempted revision, what was said, and
which objections have later verification evidence rather than a blanket claim.

**Independent Test**: Exercise the real scoring loop with controlled provider
responses, then assemble reports from persisted records after the loop closes.

**Acceptance Scenarios**:

1. **Given** a scoring job has a malformed reply, a gate-contradicting reply and a later valid reply, **When** the real re-ask path completes, **Then** committed tests prove every evaluation retains identity, model/route, scenario results, bounded feedback, parse/transport status, tested revision and criteria fingerprint; only the existing loop decides the final verdict.
2. **Given** multiple transport deliveries or judge re-asks share one gateway key, **When** their records are aggregated, **Then** tests prove job-level usage is counted once, supported request-level usage is attributed only to its real call, and missing per-call metrics remain unknown rather than an invented division of the job total.
3. **Given** a scenario objection followed by verification of the same criterion and a later revision, **When** the report is assembled, **Then** a committed test proves the resolution links the objection to that exact later evaluation and revision; the original objection remains readable.
4. **Given** changed criteria, no judge, unavailable judge, contradictory gate findings, narrative feedback without a scenario, or an operator disposition, **When** the report is assembled, **Then** parameterized tests prove each stays distinct from verified-fixed; unrelated green CI and a composed PASS cannot label all objections fully fixed.
5. **Given** attempts containing gate commands, statuses, timings, bounded output and file changes including additions, modifications, renames, deletions and binaries, **When** a report is assembled, **Then** tests prove it names actual run evidence and exact base/attempted/verified revisions, distinguishes truncated logs and absent coverage, and never infers coverage from a test-file count.

### User Story 3 - A story packet exports and verifies without a running factory (Priority: P1)

As an operator, I can export one self-contained packet and verify its retained
contents without Temporal, the original worktree or a provider connection.

**Independent Test**: Export from a temporary evidence root, relocate the archive,
remove only that test's source worktree, and verify offline through the real CLI.

**Acceptance Scenarios**:

1. **Given** an attributable story with a failed and successful attempt and selected declared artifacts, **When** the real export command runs, **Then** committed tests prove the ZIP contains a versioned JSON manifest, readable report and exact selected bytes with identities and SHA-256 digests, and verification succeeds with network disabled after relocation.
2. **Given** identical evidence exported twice, **When** archive bytes are compared, **Then** a committed test proves reproducible bytes; new evidence produces a successor revision referencing its predecessor and leaves the original unchanged.
3. **Given** missing, expired, oversized or refused evidence, **When** export completes, **Then** tests prove each requested item has a reason and completeness status rather than disappearing; strict completeness returns a nonzero result without reclassifying the build.
4. **Given** traversal, escaping or substituted symlinks, hardlink aliases, special files, duplicate archive names, unlisted ZIP entries, oversized/expanded archives or corrupted bytes, **When** capture, export or offline verification encounters them, **Then** committed tests prove bounded refusal without following unsafe paths, extracting content, overwriting another packet, or hanging on a FIFO.
5. **Given** credential-shaped text, private absolute paths, raw CLI transcripts and active HTML in evidence, **When** a private report is exported, **Then** tests prove text redaction/escaping, exclusion of raw transcripts and homes, owner-only storage, and no automatic network/public upload; selected opaque bytes retain a sensitivity warning, not a false claim of safe redaction.

### User Story 4 - Lifecycle completion produces recoverable packets (Priority: P1)

As an operator, I receive packets automatically when a node or epic finishes,
including unsuccessful work, without a packet failure changing the ladder.

**Independent Test**: Run the workflow against real temporary journal/archive
activities with controlled coding and forge peers; exercise cleanup and restart.

**Acceptance Scenarios**:

1. **Given** a configured packet policy and a node reaching MERGED, terminal PASSED without landing, FAILED or KILLED, **When** its lifecycle completes, **Then** committed tests and a bounded pasted trace prove worktree evidence is captured before cleanup and a terminal packet is generated after usage teardown with that exact outcome.
2. **Given** a worker restart, workflow replay or redelivered finalization, **When** processing resumes, **Then** tests prove one logical packet revision per evidence set, a recoverable pending/failed status, no filesystem/network calls in workflow replay, and no duplicate model invocation caused by packet work.
3. **Given** collection fails or finalization exhausts its finite retry bound, **When** normal cleanup and build completion proceed, **Then** tests prove the original salvage, key teardown, node outcome and ladder accounting are unchanged, the gap remains visible, and an explicit finalize retry can use retained evidence without recoding the node.
4. **Given** an epic closes with mixed outcomes, including nodes never launched, **When** its packet is finalized, **Then** a committed test proves it lists all nodes and their packet references or explicit missing/not-run reasons; epic COMPLETED is never rendered as all stories landed.
5. **Given** a dispatch with packet generation disabled, an older in-flight history, or an invalid new packet configuration, **When** the same entry points run, **Then** tests prove explicit disabled/legacy status, replay-compatible old behavior, and invalid new configuration refused before dispatch rather than silently defaulted.

### User Story 5 - A spec packet includes reruns without counting work twice (Priority: P2)

As an operator, I can export the whole spec at a named revision, including its
earlier failed work and the current selected landed content for each story.

**Independent Test**: Assemble a two-story spec from two closed epic executions,
one partially landed, and compare the result with independently computed inputs.

**Acceptance Scenarios**:

1. **Given** one epic lands US1 and fails US2, and a second lands the remainder, **When** the named spec-revision packet is exported, **Then** committed tests prove each selected story revision appears once, all included epic executions are listed, and all attributable builder/judge usage from both executions is counted once.
2. **Given** an amended story, an attested baseline without attempt evidence and an observed landing, **When** the rollup is built, **Then** tests prove each content fingerprint and provenance is preserved; selecting a newer story does not delete old spend or invent baseline judge/usage records.
3. **Given** two targets use the same spec name or the caller omits the desired revision/selection, **When** rollup resolution runs, **Then** tests prove cross-target records are excluded and ambiguous selection is refused instead of inferred from current checkout HEAD.
4. **Given** one story packet is missing or partial and another is complete, **When** the spec archive is exported and independently verified, **Then** a committed test proves completeness propagates by required dimension, known subtotals remain labeled partial, and every nested packet digest and selected revision is checked offline.

### User Story 6 - Teams attach their CI and audit reports to immutable revisions (Priority: P2)

As a team, I choose the evidence my delivery process needs and can add later
test/scan reports without overwriting the original story or spec history.

**Independent Test**: Invoke the attachment and export CLI from a fixture CI
workspace against a local evidence root; inspect the new and previous archives.

**Acceptance Scenarios**:

1. **Given** team policy selects integration, UAT, security, code quality and SBOM evidence, **When** the real CLI attaches local report bytes with an explicit subject, tested revision, run identity, producer, submitter and claimed status, **Then** committed tests prove a new immutable packet revision retains those bytes and metadata without interpreting or executing the reports.
2. **Given** branch CI and merge-group CI tested different commits, **When** their evidence is attached, **Then** tests prove both tested revisions, run IDs and relationships to the attempted/landed content survive; a branch-green result is not presented as native merge-group qualification.
3. **Given** mismatched target/revision, unknown subject, a repeated delivery, a same delivery ID with different bytes or concurrent submissions, **When** attachment runs, **Then** tests prove refusal of mismatches/conflicts, idempotent identical repeats, no lost attachments and unchanged prior packet bytes.
4. **Given** a team requires complete packets before publication and selects a private CI artifact destination, **When** the documented CI example exports and checks a fixture packet, **Then** committed executable tests prove the completeness exit contract and named downloadable artifact; no default public destination, URL fetch, hosted endpoint or scanner account is created.
5. **Given** later UAT attaches to a story already referenced by a spec packet, **When** rollup is refreshed, **Then** a committed test proves a successor spec packet selects the new story packet and explicitly preserves its predecessor rather than silently mutating the old rollup.

## Functional Requirements

- **FR-001**: Evidence MUST identify declared target, spec revision/fingerprint, epic workflow and run, node, invocation, ladder ordinal, phase/form and scoring job/call as applicable; new records MUST survive reused ordinals and execution IDs MUST NOT be derived from wall-clock guesses.
- **FR-002**: The journal MUST capture the frozen ladder and ordered actual persona/runner/route/model selections and transition reasons; dispatched aliases MUST remain distinct from observed serving-model/fallback evidence and unavailable dimensions MUST be named.
- **FR-003**: Every launch path, including pre-agent/issuance failure, question, timeout and cancellation, MUST be recorded without requiring verification and without changing existing ladder charging, route, key confinement or cleanup policy.
- **FR-004**: Usage MUST be source-labeled per dimension with builder/judge separation, known subtotals and completeness; gateway and CLI counts MUST NOT be added together, overlapping token dimensions MUST NOT be counted twice, ambiguous legacy joins MUST be refused and unavailable subscription dollars MUST NOT become zero.
- **FR-005**: Every judge evaluation and observable request retry MUST retain its identity, criteria/tested revision, result or failure and bounded feedback; scoring-job totals MUST be counted once and missing per-call detail MUST NOT be fabricated.
- **FR-006**: Resolution MUST link an original objection to later verification of the same criterion or an explicit separately labeled disposition; changed criteria, unjudged PASS and unrelated CI MUST NOT establish verified-fixed or fully-fixed.
- **FR-007**: Reports MUST retain raw structured judge outcomes, composed verdict, unavailable/skipped state, gate contradictions, gate commands/status/timing/log completeness and exact base/attempted/verified file manifests, including additions, changes, renames, deletions and binary paths.
- **FR-008**: A packet MUST contain schema version, stable subject identity, immutable content revision, readable report, JSON manifest, selected attachment bytes and per-entry SHA-256 digests; identical evidence MUST export reproducibly and verify offline without extraction.
- **FR-009**: Requested missing/expired/refused/oversized evidence MUST remain visible, and strict completeness MUST return nonzero without rewriting a build result; retention MUST default to preserve and never silently delete evidence.
- **FR-010**: Capture/export/verification MUST enforce containment, regular-file and archive bounds, safe names, no alias/overwrite and integrity checks; text MUST be redacted/escaped, raw CLI archives/homes/credentials/private absolute paths MUST be excluded, and opaque attachments MUST require explicit selection with honest sensitivity metadata.
- **FR-011**: Packet storage MUST be owner-only and private by default; generation/export MUST NOT upload, fetch arbitrary URLs, execute report content or modify the public PR evidence policy.
- **FR-012**: Factory lifecycle integration MUST acquire ephemeral evidence before cleanup, finalize after teardown/terminal outcome, and cover node and epic completion including failed, killed, halt-after-pass and not-run cases.
- **FR-013**: Collection/finalization MUST use bounded idempotent activities and durable pending/failed/completed status; failures MUST preserve normal salvage, cleanup, coding-rung accounting and build outcome, with an explicit retry over retained evidence.
- **FR-014**: Packet configuration MUST be declared and frozen at dispatch with finite limits and explicit enabled/disabled state; old histories MUST remain replay-compatible and invalid new declarations MUST be refused before model work.
- **FR-015**: A spec rollup MUST pin target/spec revision and contributing executions, select each story's content once, retain all attributable historical spend once, distinguish attested from observed landings, and propagate incomplete coverage without inventing evidence.
- **FR-016**: A local CI attachment interface MUST require explicit subject, tested revision, run/delivery identity, producer, submitter, claimed status and content digest; mismatches/conflicts MUST be refused and concurrent/idempotent submissions MUST preserve all accepted evidence.
- **FR-017**: Branch, merge-group, landed and post-landing test revisions MUST be distinct, with explicit relationships; late evidence MUST create successor story/spec packet revisions and MUST NOT overwrite a previous archive.
- **FR-018**: Team policy MUST select desired report categories, inclusion/size/retention values and optional completeness requirements; documented CLI/CI examples MUST be exercised and MUST allow a team's existing artifact store without adding a hosted service or generic listener framework.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010, FR-011]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-012, FR-013, FR-014]
US5:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-015]
US6:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-016, FR-017, FR-018]
```

All shared runtime/store/CLI changes are merge-ordered. No new parallel scheduler
or implied pass-edge supplies content. Re-slice before dispatch if any story's
implementation plus tests and pasted evidence cannot fit the 64 KiB diff bound.

## Out of Scope

Generic124 listener registry, per-turn event fan-out, arbitrary plugins, a new
web dashboard/download server, vendor-specific scanners, automatic public upload,
signing identities/notarization/compliance certification, interpreting report
truth, admitting artifacts into the judge prompt, and fabricated historical data.
Digests establish internal integrity, not authenticated producer identity or
proof the software is defect-free. No new real-account qualification is implied.
