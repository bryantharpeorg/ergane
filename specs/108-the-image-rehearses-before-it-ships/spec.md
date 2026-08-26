---
state: landed
fixes:
  - release/the-image-half-of-a-release-has-no-rehearsal-and-runs-after-the-irreversible-half
#
# Attested landed 2026-08-25. US1 bcee81510bb5 (#340), US2 8b8b9bc1bd06 (#341) —
# both observed on ergane-buildout by content, not by a merged flag.
#
# THE SPEC'S OWN ACCEPTANCE TEST RAN, AND IT CAUGHT SOMETHING. This is the rare
# case where the `fixes:` key above is more than a claim: `gh workflow run
# test-release.yml` was executed twice on the night US1 landed, and the first run
# failed at FR-019 —
#
#   PACKAGE-VISIBILITY-FAIL: expected public, observed private
#
# A new GHCR package defaults to private, and nothing else in the release
# pipeline looks at package visibility. Had `v0.4.0` been tagged two hours
# earlier — which was the plan before this spec existed — the wheel would have
# gone to PyPI irreversibly, pointing at an image that refuses every user who is
# not the operator. That is failure mode 13 arriving in the one direction 105's
# job ordering could not protect. The operator flipped the package to public and
# the re-run went green end to end.
#
# FR-019 was added to this spec THREE HOURS before it fired, during a refinement
# pass (#339) prompted by a hand probe of the registry. The probe pushed a
# throwaway image under a deliberately different name and found
# `visibility=private repo=UNLINKED`, which falsified the working assumption that
# a public repository yields a public package. Had the probe used the real name
# to be maximally informative, it would have created an unlinked `ergane` package
# and denied the release workflow the write it needs — manufacturing the blocker
# it was testing for. That near-miss is trap T8 in the plan.
#
# MEASURED, and worth keeping: the multi-arch build including the emulated
# linux/arm64 layer took 489s and 527s across two rehearsal runs, and 511s on the
# real release. Against `timeout-minutes: 90` that is under 10% of the budget, so
# the ceiling is generous rather than tight. Nobody had this number before; it is
# what FR-007 exists to produce. A 48-minute figure measured locally on the
# factory host is NOT comparable — that build carried 11.8 GB of `.ergane` node
# homes that CI's 20 MB tracked-files checkout does not have
# (container/dockerignore-omits-ergane-so-a-local-build-ships-node-homes).
#
# COST: two stories, three attempts. US1 passed first time. US2 took two, and
# THE SECOND ATTEMPT WAS EARNED — this entry originally said otherwise and was
# corrected on 2026-08-26 after the workflow history was read rather than
# inferred.
#
# US2's attempt 1 (commit 887bc05) passed the full 4,934-test gate and was then
# FAILED BY THE JUDGE, correctly. FR-015 required the GHCR-login assertion to
# pin one resolved answer. The agent replaced the old `or` with
#
#     any(f"registry: {host}" in job_text for host in ghcr_hosts)
#     ghcr_hosts = ("ghcr.io", "${{ env.IMAGE_REPOSITORY }}")
#
# and reported it as "tightened to one resolved answer". The judge read the diff
# and said: "functionally identical to the old `or` — it still accepts two
# alternatives and pins neither." Attempt 2 resolves the value instead: it loads
# the workflow, reads `build-and-publish-image`'s `IMAGE_REPOSITORY`, and asserts
# that it resolves to the GHCR host. One answer.
#
# THAT IS THE JUDGE EARNING ITS PLACE IN THE PIPELINE, and it is worth naming
# because a permissive assertion passes every test. The gate was green on a diff
# that did not meet its requirement, and nothing deterministic could have caught
# it — the defect was that an assertion accepted too much, which is invisible to
# a test run and visible to a reader. Principle: a green suite is evidence, not
# proof.
#
# Two `[TMPRL1101] Potential deadlock detected` workflow-task failures appear in
# this epic's history (ev287 02:06:46Z, ev434 02:21:46Z), both ~5 minutes into a
# ~6 minute gate. They cost nothing — all 86 activities completed, Temporal
# retried the workflow task, both nodes landed — and they are unrelated to the
# attempt-1 failure above. Filed as
# workflow/temporal-deadlock-detector-fires-during-long-gates.
#
# Both nodes ran persona `implementer` on `ollama-cloud/kimi-k2.7-code`,
# gateway-routed and billed per token. Attempt spend, from the workflow's own
# snapshots: US1 $6.65, US2 attempt 1 $1.47, US2 attempt 2 $3.06.
#
# THE WORKFLOW-SCOPE FINDING IS NOW STALE. US1 writes
# .github/workflows/test-release.yml and landed through the factory without
# incident, which is the first time a story touching that directory has done so.
# `merge/a-story-touching-github-workflows-cannot-be-pushed-by-the-factory` was
# opened when the target clone pushed over HTTPS with an OAuth App token; the
# operator repointed it to SSH and this landing is the evidence that closes it.
#
# DRAFTED 2026-08-25 ~7:30 PM CT by the operator session, against ergane-buildout
# at 6d3b3d3 (0.4.0 declared, main converged). Written because the operator asked
# to test a GHCR push before cutting v0.4.0, and the measurement behind that ask
# turned out to be worse than the ask: the image half of a release has no
# rehearsal at all, and it runs after the half that cannot be undone.
#
# ANCHOR STATUS: every file:line in the plan was read from 6d3b3d3 on 2026-08-25
# and is current as of drafting. Re-verify before dispatch if the branch has
# moved.
#
# THIS SPEC IS ALSO A TEST OF THE FACTORY. US1 writes
# .github/workflows/test-release.yml. No story since 105/US1 has touched a
# workflow file, and 105/US1 was unlandable by construction — the factory pushed
# over HTTPS with an OAuth App token carrying no `workflow` scope, and GitHub
# refuses such a push
# (merge/a-story-touching-github-workflows-cannot-be-pushed-by-the-factory). The
# operator repointed the target clone's push URL to SSH on 2026-08-25 and every
# factory push since has used it, but none has carried a workflow file. US1 is
# the first one that will. If the finding is stale, US1 lands and closes it. If
# it is not, US1 dies at the landing step with its work intact and US2 — which
# touches no workflow file — is unaffected. The split is deliberate.
#
# Settled at drafting:
#   - The rehearsal PUSHES. A build that is not pushed does not test the push,
#     and the push is the thing with no evidence behind it. It pushes to a tag
#     nobody can depend on.
#   - The rehearsal tag is `rehearsal-<run_id>`, never a version tag and never
#     `latest`. 105's ruling — versioned tags are immutable and `latest` is for
#     humans — is extended, not reopened.
#   - The preflight build is amd64-only and NATIVE. Its job is to catch a
#     Dockerfile that cannot build at all, which is what actually happened
#     (`useradd -u 1000` against a base image that already owns uid 1000, fixed
#     in 4956123). Building both platforms twice would double the emulated arm64
#     cost, which is the one number this spec cannot yet bound.
#   - arm64 duration is REPORTED, not optimized. Nobody has measured it. A cache
#     added before a measurement is a guess with a maintenance burden.
#   - The rehearsal never deletes what it pushed. `packages: delete` is a
#     strictly larger credential than this job needs, and the `rehearsal-` prefix
#     is what makes the leftovers obviously disposable. Cleanup is an operator
#     act, documented, not automated.
#
# REFINED 2026-08-25 ~8:00 PM CT, after the operator granted the operator token
# `write:packages` so the registry could be measured rather than assumed. Three
# facts came back, and two of them added requirements:
#
#   1. TRAP T3 IS SETTLED. The organization does NOT forbid creating container
#      packages. `bryantharpeorg` held zero packages of every type (container,
#      npm, maven, rubygems, nuget, docker — all `0`), so nothing could be
#      concluded by reading; a throwaway push under the deliberately-different
#      name `ghcr-preflight-probe` succeeded. The trap stays in the plan as a
#      narrower hazard, because a 403 is still possible for a reason that is not
#      org policy.
#   2. A PACKAGE CREATED BY A PAT IS UNLINKED. The probe came back
#      `visibility=private repo=UNLINKED`. GHCR grants a workflow's
#      `github.token` access to packages LINKED to that repository, so a
#      hand-created `ergane` package would have denied the release workflow the
#      write it needs — the probe would have manufactured the blocker it was
#      testing for. This is why the probe used a different name, and it is why
#      FR-018 and trap T8 now exist.
#   3. NEW PACKAGES DEFAULT TO PRIVATE. `bryantharpeorg/ergane` is a public
#      repository, so a package created by Actions and auto-linked to it should
#      inherit public visibility. SHOULD. Nobody has observed it, the workflow
#      asserts nothing about it, and a private release image is failure mode 13
#      wearing a different coat: a public CLI pointing at an image that refuses
#      every user who is not the operator. FR-019 exists to make the first
#      rehearsal answer it.
#
# NOT A DEFECT — tested and withdrawn before drafting. The GHCR login passes
# `registry: ${{ env.IMAGE_REPOSITORY }}` (= ghcr.io/bryantharpeorg/ergane)
# rather than the bare host. Docker normalizes the path away: both that form and
# `docker login ghcr.io` contact https://ghcr.io/v2/, and a successful path-form
# login into an isolated DOCKER_CONFIG stored the credential under the key
# `ghcr.io` — which is the key buildx looks up at push time. The line is correct
# and this spec does not change it. It appears here only so a future reader does
# not re-derive the suspicion.
---

# Feature Specification: the image rehearses before it ships

**Created**: 2026-08-25
**Depends on**: 105 (landed). US1 and US2 are independent of each other.

## The gap, stated precisely

`.github/workflows/test-release.yml` opens by stating the doctrine this
repository releases under:

> It exists so the first real publish is not the first publish.

It then applies that doctrine to the wheel and not to the image. The rehearsal
workflow contains no `buildx`, no `ghcr`, and no `cosign` — zero occurrences of
any of the three. Meanwhile `.github/workflows/release.yml:76-77` orders
`build-and-publish-image` behind `needs: [build-and-publish]`, so on the next
`v*` tag the sequence is:

1. the wheel uploads to PyPI — **irreversible**, because PyPI refuses reuse of a
   name-and-version pair forever;
2. *then*, for the first time in this repository's history, a GHCR push runs, a
   `linux/arm64` layer builds under QEMU emulation against `timeout-minutes: 90`,
   and cosign signs keyless over OIDC.

Any one of those three failing produces a published CLI pointing at an image that
404s. That is failure mode 13 — the exact outcome 105 was written to prevent —
arriving in the one direction 105's job ordering cannot protect, because the
protection runs after the damage.

**This is not theoretical.** The image did not build at all until 2026-08-25.
`Dockerfile`'s `useradd -m -u 1000 ergane` failed with `UID 1000 is not unique`
on `ubuntu:24.04`, which already owns that uid, and it survived 25 landed stories
because every container test in the tree parsed the Dockerfile as **text**.
`test_dockerfile_runs_as_non_root` read the `USER 1000:1000` line two lines below
the broken one and passed. It was found by running `docker build`, and it was
fixed in `4956123`. The lesson generalises exactly once: **an artifact nobody
produces is an artifact nobody has tested**, and the pushed, signed, multi-arch
manifest is still such an artifact today.

## The rule this spec is asking for

**Before a version tag is ever cut, an operator can push a real multi-arch image
to GHCR, sign it, and read back the manifest — under a tag nothing depends on.
And when the real tag is cut, nothing irreversible happens until the image has
been proven buildable.**

### The ruling, made here rather than left to the implementer

- **The rehearsal lives in `test-release.yml`, not a new file.** That workflow is
  already `workflow_dispatch`-only, already carries the "first real publish is
  not the first publish" contract, and is already the file the publish-containment
  guard inspects. A second rehearsal file would be a second thing to keep in
  sync.
- **The trigger does not widen.** `on: workflow_dispatch:` and nothing else.
  `tests/test_release_path.py:520` scans every workflow for the word `publish`
  and requires the match to be operator-triggered only;
  `_workflow_is_operator_tag_trigger_only` (`:272-296`) permits `workflow_dispatch`
  explicitly, so the guard stays green **provided the trigger is not touched**.
- **The rehearsal is the release job's twin, not its cousin.** Same single
  `docker buildx build --platform linux/amd64,linux/arm64 --push` invocation, same
  cosign-over-digest, same `imagetools inspect` platform assertion. A rehearsal
  that exercises a different code path rehearses nothing.
- **The tag is `rehearsal-<run_id>`.** Never a semver tag, never `latest`. A
  committed test forbids the rehearsal job from ever emitting a tag matching
  `^[0-9]+\.[0-9]+\.[0-9]+$`.
- **The preflight is amd64-only and native.** It exists to fail a release before
  PyPI when the Dockerfile cannot build. The realistic failure — the one that
  actually happened — fails on amd64 just as surely as on arm64, and native amd64
  costs minutes where emulated arm64 costs an unmeasured amount.
- **Duration is reported, not optimized.** The rehearsal prints its own wall time
  against the timeout so the arm64 number stops being a guess.

## User Scenarios & Testing

### User Story 1 - The rehearsal pushes an image nobody depends on (Priority: P1)

As the operator, before I spend a version number I can run one workflow that
pushes a real signed multi-arch image to GHCR under a throwaway tag, and read
back what it produced.

**Acceptance Scenarios**:

1. **Given** the committed `test-release.yml`, **When** a drift test reads it,
   **Then** a second job exists carrying one `docker buildx build` invocation
   that declares `--platform linux/amd64,linux/arm64` and `--push`, a GHCR login
   using `github.token`, a `packages: write` permission on that job's own
   `permissions:` block, a cosign keyless signature over the pushed digest, and
   an `imagetools inspect` assertion naming both platforms — red first with any
   one element removed, green against the committed file.
2. **Given** the same job, **When** the test reads the tag it pushes, **Then**
   the tag derives from `github.run_id` and carries the literal prefix
   `rehearsal-`; and **no** value the job can emit matches
   `^[0-9]+\.[0-9]+\.[0-9]+$` — proven by a committed test that would fail if the
   job were pointed at a version tag.
3. **Given** the whole workflow file, **When** the publish-containment guard at
   `tests/test_release_path.py:520` runs, **Then** it still passes, because the
   `on:` block is still `workflow_dispatch:` alone — proven by that existing test
   remaining green, unmodified.
4. **Given** the rehearsal job runs, **When** it finishes the build step,
   **Then** it prints the elapsed build seconds and the configured
   `timeout-minutes` in one line, so the arm64 cost is a measurement rather than
   an assumption.
5. **Given** an operator on a host with no GHCR access, **When** they read the
   committed workflow, **Then** the job's own comment names what credential it
   uses and states that none is stored in this repository — the same claim
   `build-and-publish-test` already makes about PyPI.
6. **Given** the rehearsal has pushed, **When** the job reads the package back
   from the GitHub API, **Then** it asserts the package's linked repository is
   this repository and exits non-zero naming both values if it is not — because
   GHCR authorises a workflow token against packages **linked** to its
   repository, and an unlinked package silently denies the next push. Measured
   2026-08-25: a package created outside Actions comes back `repo=UNLINKED`.
7. **Given** the same package, **When** the job reads its visibility, **Then** it
   asserts `public` and exits non-zero naming the package settings page if it is
   not — because new packages default to private, and a private image published
   against a public CLI is unreachable for every user who is not the operator.
   Neither assertion may be satisfied by a hardcoded owner or package name:
   both derive from the single `IMAGE_REPOSITORY` declaration and the running
   workflow's own repository.

### User Story 2 - The irreversible step goes last (Priority: P1)

As the release pipeline, I refuse before I publish rather than after, and my
drift tests pin one answer instead of accepting two.

**Acceptance Scenarios**:

1. **Given** `release.yml`, **When** a drift test reads the job graph, **Then** a
   preflight job builds the image for `linux/amd64` **without** `--push`, and
   `build-and-publish` declares `needs:` on it — so a Dockerfile that cannot
   build fails the release before anything reaches PyPI. `build-and-publish-image`
   still declares `needs: [build-and-publish]`, and 105's
   `test_us1_image_job_exists_with_correct_needs` passes unmodified.
2. **Given** the preflight job, **When** the test reads it, **Then** it declares
   **no** `packages: write` and performs **no** push — a job that only proves
   buildability must not hold a credential that can publish.
3. **Given** `tests/test_release_path.py:393-403`, **When** the GHCR-login
   assertion is read, **Then** it no longer accepts two alternatives via `or`.
   The current form —
   `assert ("registry: ghcr.io" in job_text or "registry: ${{ env.IMAGE_REPOSITORY }}" in job_text)` —
   passes whichever value is present and therefore pins neither. The replacement
   asserts one resolved answer, and a committed control proves it goes red when
   the login registry is changed to something that does not resolve to the GHCR
   host.
4. **Given** the whole release workflow, **When** the suite runs, **Then** every
   test 105 landed still passes without modification — this story changes what
   the pipeline *orders* and what one assertion *accepts*, not what the image job
   *is*.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  concurrent_with: [US1]
```

`concurrent_with` is declared because the validator's `slice_contention` layer
reads a task's **prose mentions** of a path as membership in that task's slice,
and US1's tasks necessarily name `.github/workflows/release.yml` (the job it
copies from) and `tests/test_release_path.py` (the guard it must leave green).
US1 **reads** both and **edits** neither. The declaration says so, rather than
letting the inference serialise two stories that do not collide.

Both stories are independent and touch disjoint files: US1 owns
`.github/workflows/test-release.yml` and a new `tests/test_release_rehearsal.py`;
US2 owns `.github/workflows/release.yml` and `tests/test_release_path.py`. There
is no `depends_on_merged` edge because neither needs the other to exist. See the
plan's contention note for the one direction they observe each other.

## Requirements (summary — numbered at refinement)

Rehearsal job identity and location; single multi-arch buildx push; throwaway tag
grammar and the semver prohibition; GHCR login credential; per-job
`packages: write`; cosign keyless over the digest; platform assertion; duration
report; **package repository-linkage assertion; package visibility assertion**;
trigger non-widening; preflight job shape, platform and credential floor;
`build-and-publish` gaining `needs:`; the login assertion tightened to one answer
with a red-first control.

## Success Criteria (summary)

Pasted: the US1 drift suite red-then-green with each required element removed in
turn; the US2 login-assertion control red against a wrong registry and green
against the committed one; 105's release tests passing unmodified in both
stories.

**Operator verification, which is the point of the spec**: `gh workflow run
test-release.yml` completes; `docker buildx imagetools inspect
ghcr.io/bryantharpeorg/ergane:rehearsal-<run_id>` reports both `linux/amd64` and
`linux/arm64`; `cosign verify` accepts the signature; the package reads back
`repository.full_name = bryantharpeorg/ergane` and `visibility = public`; and the
printed build duration is recorded so the next reader of `timeout-minutes` is
reading a measurement.

Two of those can fail for reasons that are **operator settings rather than
defects in the job** — a 403 on the push, or a package that comes back private.
Both are results this spec exists to produce cheaply, under a tag nothing
depends on, instead of expensively after a version number is spent.
