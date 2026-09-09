# Codex-primary specification batch review

**Batch:** refined 087, 112, 139; new 157–162
**Endpoint:** implementation authorized; 157, 087, and 158 promoted to `ready`
**Implementation scope:** operator migration, gateway qualification, and automatic subscription upper rung as the final phase

## Outcome

The current priority is **157 → 087 → 158** for the Codex operator workflow,
with Codex builders using the existing gateway to Ollama Cloud. The earlier
159/112/160 promotion recommendation is superseded. The operator has now agreed
to implement the automatic Codex subscription upper rung as the final part of
this work, after the operator migration and Ollama gateway qualification. That
phase is scoped to the deployment actually in use, using the approved factory
login design. Broad subscription-only onboarding and additional deployment
layouts remain outside this immediate scope.

The batch and deferred governance proposal cover the nine audit findings and
all A–H work packages without
rewriting landed specs 125, 154, 155, or 156. The operator authorized execution
on 2026-09-09 and promoted 157, 087, and 158 in dependency order; the remaining
six trios stay `draft`. Mechanical validation is clean. Account-backed
qualification, client trust, deployment changes, and rollout remain evidence
to earn during their stated implementation phases.

## Author validation

Each trio was validated from `/home/admin/code/ergane` with explicit identities:

```text
ERGANE_ROOT=/home/admin/code/ergane/.factory \
  /home/admin/code/ergane/.venv/bin/ergane spec validate <absolute-spec-dir> \
  --target-repo /home/admin/code/ergane \
  --specs-root /home/admin/code/ergane/specs --json
```

Final result for each of 087, 112, 139, and 157–162:

- exit status 0;
- no findings;
- no skipped layers;
- no judge warnings;
- every acceptance scenario reported provable; and
- 112's two and 139's one declared finding keys verified against the explicitly
  selected `/home/admin/code/ergane/.factory/doctor.db`.

Each trio was then derived with the same explicit target/spec roots and `--json`
but no `-o` and no `--delta`. After the gateway-first scope correction, all nine derivations exited 0, produced 39 total
story nodes, included every declared FR key, preserved explicit merged edges,
and inferred no edges. This was deliberately a no-artifact-write pass. In
particular, the pre-existing stale 112 `workgraph.json` remains preserved and
must not be dispatched; the later authorized dispatch preparation must derive
and inspect a written replacement.

`git diff --check` is clean for tracked changes. No code or runtime test suite
was run because this batch changes specifications and supporting documents only;
the executable verification work is stated test-first in each trio.

## Validation objections and repairs

The first validator pass raised three classes of refusal. All were repaired and
the complete nine-trio pass was rerun:

1. Dependent work-graph declarations carried `depends_on_merged` but omitted the
   schema-required explicit `depends_on: []`. The empty immediate-edge list is
   now present beside every merged edge.
2. 139 FR-022 used permission wording (`MAY`) without a testable obligation. It
   now requires that only separately authorized real-client qualification be
   permitted to produce `verified active enforcement`.
3. 159's plan rendered a module constant as a symbol-tier anchor even though the
   validator recognizes Python definitions/classes at that tier. It now cites
   the exact test line as statement evidence without asserting a nonexistent
   symbol span.

## Coverage and ownership decisions

- 157 owns repository operator orientation and shared workflow/capability
  language. Subscription governance is preserved in the deferred proposal and
  requires a separately scoped implementation before subscription rollout.
- 087 owns collision-safe operator-skill packaging only; 158 owns the corrected
  behavior of read/report/authorized-action jobs.
- 139 owns target-repository safety context and client hook bindings, explicitly
  excluding root operator instructions and copied Python checkers.
- 159 owns credential authenticity, serialized durable ownership, refresh
  finalization, route cleanup, and shared status. 112 consumes that status and
  owns control-plane `none`, readiness, and install interview behavior.
- 160 owns current-attempt Codex JSONL evidence/classification/usage for either
  route, independently of 159; 161 owns
  deployed credential/toolchain/confinement qualification and the held real
  pilot.
- 162 owns away-mode state, authority, journaling, client bindings, stop, and
  recovery while preserving Temporal as the factory scheduler.

The audit's F1–F9 and A–H mapping is recorded in section 10 of
`docs/codex-primary-audit-plan-2026-09-09.md`. The complete skill inventory and
dispositions are in
`docs/codex-primary-operator-migration-runbook-2026-09-09.md`.

## Recommended implementation order

1. **157:** canonical operator contract and capability map, with fresh-client
   discovery as completion evidence. The former unlanded governance US3 was
   removed from this trio; its scope is preserved in the deferred proposal.
2. **087:** installable shared operator-skill source and client bindings; waits
   for 157 to land.
3. **158:** correct read/report and declared-action skill behavior; waits for
   157 and 087 to land.
4. **160:** current-attempt evidence on the existing gateway path, independent
   of subscription credential ownership. This work can proceed alongside the
   operator lane.
5. **139:** target context/checker/bindings after 157; qualify actual hook
   trust/enforcement separately.
6. **Later gateway cutover:** qualify Codex CLI through the existing LiteLLM
   gateway and selected Ollama Cloud alias on the actual deployment, including
   tool use, gates, judge, archive, attribution, cancellation, and queue landing.
   The source path already exists; its current deployed behavior was not tested
   in this documentation pass.
7. **Final phase — automatic subscription upper rung:** implement 159's
   credential lifecycle, reuse 160's attempt evidence, and qualify a focused
   current-deployment slice of 161. The configured ladder selects the Codex
   subscription persona automatically within its bounds. Completion includes
   refresh persistence, concurrent-rung admission, bidirectional route cleanup,
   cancellation/restart recovery, and a real gate/judge/landing record.

Before preparing the final phase for dispatch, narrow 161's existing broad
trio and dependencies to the selected deployment and reconcile the proposed
target/governance policy for that qualification. Its current dependency on
112 and all-layout scope are not requirements of the agreed upper-rung feature.
112's subscription-only onboarding and 162's optional unattended assistance
remain outside this sequence; neither is required to complete the final rung.

## Current execution state

- The live roadmap was queried through the configured operator environment on
  2026-09-09: it was paused, with no running or parked epic.
- Specs 131 and 147 were already `ready`. The Codex sequence therefore uses
  deliberate per-spec dispatch while the roadmap stays paused, so resuming it
  cannot advance unrelated ready work.
- 157 runs first. 087 and 158 are ready but remain dependency-blocked until
  their predecessors land.

## Genuine holds

- Promotion beyond the agreed first three remains phase-gated by the execution
  order and the evidence produced by preceding landings.
- The private target and GitHub Enterprise Cloud queue qualification are
  unresolved choices in the proposed pilot policy, not blockers for the gateway
  path. The final phase must reconcile that proposal with the selected target.
- The proposed next-decision/constitution amendment (`D-056` only at the current
  fingerprint) is deferred and not approved; it no longer gates 157. All existing
  decisions including D-053 are preserved.
- No real Codex account/model entitlement, auth refresh, container/host layout,
  hook trust/enforcement, or client instruction discovery has been qualified.
- The roadmap remains paused intentionally while the Codex sequence uses
  deliberate per-spec dispatch. At this checkpoint no build or dispatch,
  service or installed-skill change, findings mutation, attestation, commit, or
  push has yet occurred.

The final-phase implementation scope and the first three promotions are agreed.

## Operator follow-up and scope correction — 2026-09-09

The operator approved the modified Codex login arrangement: a separately created
factory login session and credential directory, with one host-global durable
serialized owner across local targets and deployment shapes. This records design
approval; no login was performed or credential changed. Sessions sharing that
credential must run serially. Pilot-target selection and the broader governance
amendment remain deferred.

The subsequent clarification makes the immediate builder declaration
`agent: codex`, `route: gateway`, and the operator-selected `ollama-cloud/...`
alias. The operator pane uses Codex CLI with independently configured inference.
The former recommendation over-prioritized subscription ownership and is replaced
by 157/087/158. At that point no spec state or live configuration had changed.

To make that recommendation concrete, 157's former draft governance US3 and its
three requirements were moved out of the trio into the deferred proposal, with
no identifier reuse. 160 now uses the landed neutral result and a field-enumerating
preservation contract, so future 159 owner/generation fields are not prerequisites
for gateway evidence. Fresh-client discovery remains mandatory to complete 157;
it is not required before authoring or promoting its implementation contract.

The operator further specified the deferred subscription use: a configured
automatic upper rung, as previously used for Claude subscription auth. The
existing ladder selects a persona declaring `agent: codex`,
`route: subscription`, and an explicit account-supported model; the configured
order and attempt bounds remain authoritative. The assistant's suggested
per-rescue approval action is rejected and is not implementation scope.

159-US2 and 161-US4 now explicitly require automatic selection and negative
controls for absent, disabled, or exhausted promotion. Credential serialization,
route cleanup, refresh persistence, and current-attempt evidence remain the
technical gaps. Model fallback aliases do not encode a runner/route switch;
that switch belongs to the selected persona. The top-three recommendation
remains 157/087/158, with subscription activation sequenced last. These follow-up
scenario additions were mechanically validated; the independent review below
predates these additions.

The operator then accepted implementing that automatic rung as the last part
of this work. This supersedes indefinite deferral of 159 and the focused 161
qualification. Preserve the existing ladder, ordinary Ollama gateway builders,
and independent judge; do not add per-use approval, subscription-only
onboarding, or unused deployment layouts to the final phase.

## Independent review

Two read-only reviewers examined the authored batch after validation: one for
architecture/auth/client-contract accuracy and one for story provability,
negative controls, dependency order, and rollout safety. Both final confirmation
passes reported no remaining blockers for the original 40-node batch. After the
operator's scope clarification, the provability reviewer rechecked the corrected
157 and 160 trios and reported no blockers; the 39-node batch was mechanically
revalidated. The detailed original review history below is retained; its
157-governance and 160-depends-on-159 resolutions are superseded by the scope
correction above.

### Architecture, authentication, and client-contract review

The reviewer raised six blocking objections. Their accepted resolutions were:

1. The proposed private pilot was unreachable under D-007/D-049. 161-US5 now
   defines the narrow governance-approved, operator-declared,
   organization-owned private GitHub Enterprise Cloud merge-queue cell and
   preserves refusal for public account-backed, user-owned, or unverified
   targets.
2. Offline inspection overclaimed authentication and model availability. 159
   now separates structural eligibility, eligibility to attempt refresh, and a
   provider rejection recorded from an actual prior result; 112 leaves account
   and model entitlement unqualified until 161's real pilot.
3. Codex JSONL stdout and diagnostic stderr lacked a complete backend seam. 160
   now carries separate sinks through `AgentInvocation`, `HostAgentBackend`, and
   `BwrapBackend` while retaining Claude's combined-log behavior.
4. Credential ownership was scoped too narrowly. 159 now requires one
   host-global owner keyed by declared redacted credential identity across
   epics, targets, and deployment shapes and refuses duplicate owner roots or
   hosts.
5. Several evidence anchors used unstable bare line references. Plans now use
   symbols, table rows, headings, or exact statement evidence appropriate to
   the validator.
6. The migration inventory omitted `ralph/ralph.sh`. The runbook now explicitly
   retires it as a default factory path or requires a separate spec if it is
   retained for a distinct operator job.

The reviewer also confirmed the canonical `$HOME/.agents/skills` destination,
the actual Principle V heading, draft-only runbook status, host-policy versus
child credential visibility, and the exact synchronous Codex deny response.
Their optional request to include a redacted `permissionDecisionReason` was
accepted in 139.

### Provability, dependencies, and rollout-safety review

The reviewer raised nine initial blocking objections. Their accepted
resolutions were:

1. The governance proposal now amends the actual Principle VII, places
   credential isolation under Environment Constraints, allocates a decision ID
   at application time, and treats D-056 only as the current-fingerprint
   candidate while preserving every earlier decision byte.
2. Cross-spec ordering now makes 161 consume 112/159/160 and makes 162 consume
   161, with explicit supervised-pilot and governance holds where real account
   or scheduler evidence is required.
3. The stale 112 workgraph remains preserved because this pass was forbidden
   to write derivation artifacts. A non-writing derivation proves the current
   four-node graph, and the spec, plan, tasks, and this report all prohibit
   dispatch until a later authorized written replacement is derived and
   inspected.
4. 087 distinguishes `current-filesystem` from actual client loading, and 162
   distinguishes a rendered definition, created binding, and verified
   fired/notified execution.
5. 159 permits recorded provider revocation only from an actual result, fences
   the current process group before candidate reads, tests owner
   permissions/symlinks, and implements the host-global ownership boundary.
6. 139 canonicalizes absolute, relative, parent-segment, repeated-separator,
   quoted/space-bearing, and symlink aliases; its complete Codex patch parser is
   a separate US6 slice.
7. Oversized 159 and 162 stories were split into smaller independently provable
   vertical slices.
8. 112 now requires a diff-visible focused Claude regression fixture rather
   than relying only on an unchanged broad suite.
9. The runbook and 161 now distinguish synthetic layout/confinement proof from
   a real Codex search/edit/test/commit pilot and explicitly dispose of `ralph`.

The reviewer also confirmed grounded-question abstention, hook-qualification
invalidation, raw evidence permissions/retention, real-version event
conformance, semantic round-trip proof, and the revised away-mode activation
gate. A follow-up caught one repair-induced coarse dependency: making all of
161 depend on landed 157 would have blocked US1–US3 synthetic hardening. The
frontmatter now depends only on 112/159/160, while 161-US5/US4 retain explicit
157 governance and operational holds. A final confirmation found no blocker and
confirmed that 087 points client skill-loading evidence to the runbook's
shared-discovery gate.
