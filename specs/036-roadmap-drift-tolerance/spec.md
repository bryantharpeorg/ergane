---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane-roadmap-target
# Scaffolded by `ergane findings promote` from
# `roadmap/drift-check-dies-on-spec-committed-after-landing` (critical, filed
# 2026-08-13 after the first roadmap fire since Aug 10 died on it), then
# refined by the operator session the same night against the tree at 8bdb425.
# Bryan reviews and flips ready.
---

# Feature Specification: A missing baseline is a fact to skip, not a reason to die

The roadmap's drift check renders a landed spec `amended` when its text no
longer matches what its stories landed with. To do that it pins each landed
story's fingerprint at that story's landing commit — and assumes the spec file
exists in the tree at that commit. The assumption is false for a legal and
recurring sequence: a spec that reached its agents from the operator's local
`specs_root` and was committed to the branch only after its stories landed
(010 is the proven case). For such a spec, `git show <landing-rev>:specs/<dir>/spec.md`
can never resolve, the activity raises, and the workflow awaits it unprotected
— one such spec kills the whole roadmap run, every run, and the line stalls.
That violates the roadmap's own parking principle: one bad spec must never
stall the line.

### User Story 1 - Drift degrades instead of dying (Priority: P1)

The fingerprint reader treats a spec file missing at a landing commit as "no
baseline for this fact" rather than an error; the drift computation compares
only facts that have baselines; and a drift activity that fails anyway is
caught by the workflow, rendered as not-drifted for the pass, and reported
once through the roadmap's existing failure-notice channel instead of
propagating.

**Why this priority**: the roadmap schedule is paused *today* because of this
defect — every 15-minute fire fails identically at `drift_for_spec(010)`.
Until this lands, every dispatch is a hand-run `ergane build start`.

**Independent Test**: build a scratch git repo in-test whose landing commit
predates the spec file's first commit; the drift path over it returns clean
answers and raises nothing; a scripted drift failure leaves a roadmap run
alive and dispatching.

**Acceptance Scenarios**:

1. **Given** a target repo where a story's landing commit predates the spec
   file's first commit (fixture repo: land the code-bearing commit first,
   commit `specs/<dir>/spec.md` after), **When** the baseline fingerprint for
   that fact is pinned, **Then** the result says "no baseline" and nothing
   raises — `git show`'s failure is interpreted, not propagated.
2. **Given** a spec all of whose landed facts lack baselines, **When**
   `drift_for_spec` runs, **Then** it returns not-drifted.
3. **Given** a spec with one comparable fact whose current text differs from
   its pinned baseline and one fact with no baseline, **When** `drift_for_spec`
   runs, **Then** it returns drifted — a missing baseline never masks real
   drift on the facts that can be compared.
4. **Given** the drift activity fails outright (scripted through the existing
   `_drift_runner` seam raising), **When** the roadmap computes readiness,
   **Then** the run survives, the spec renders not-drifted for that pass, the
   dispatch loop proceeds to dispatchable specs, and exactly one roadmap
   failure notice names the spec dir and the error verbatim.
5. **Given** a spec whose baselines all exist (today's happy path), **When**
   drift is computed, **Then** the answer is byte-identical to today's — the
   pre-existing drift tests pass unmodified.

## Functional Requirements

- **FR-001**: Pinning a landed fact's fingerprint at a landing commit where
  the spec file does not exist MUST yield a distinguished no-baseline result
  and MUST NOT raise.
- **FR-002**: Drift MUST be computed over facts with baselines only; a spec
  with no comparable facts is not drifted.
- **FR-003**: A drift-activity failure MUST NOT fail the roadmap run: the
  workflow treats the spec as not-drifted for the pass and reports the failure
  once, with the spec dir and the error message verbatim, through the roadmap's
  existing failure-notification path (031's channel, not a new one).
- **FR-004**: Behaviour for facts whose baselines exist MUST be unchanged;
  every pre-existing drift and roadmap test passes unmodified.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
```
