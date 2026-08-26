# Implementation Plan: the image rehearses before it ships

**Spec**: `specs/108-the-image-rehearses-before-it-ships/spec.md`
**Base**: `ergane-buildout` at `6d3b3d3` (declared version `0.4.0`; `main`
converged). Every `file:line` below was read from that commit on 2026-08-25.
**Evidence**: finding
`release/the-image-half-of-a-release-has-no-rehearsal-and-runs-after-the-irreversible-half`
(critical, opened 2026-08-25, reproduction included in its notes).

**What this spec is for, in one sentence.** The operator wants to push an image
to GHCR before spending the `v0.4.0` version number, and there is currently no
way to do that which does not also publish a wheel.

## Requirements, numbered here

`spec.md`'s Requirements section says "numbered at refinement". These are those
numbers. They live in this document because `plan.md` is one of the three files
assembled into every attempt prompt, so they reach the implementer intact.

**US1 — the rehearsal pushes an image nobody depends on**

- **FR-001**: A second job MUST be added to `.github/workflows/test-release.yml`.
  It MUST NOT be a new workflow file. It MUST NOT declare `needs:` on
  `build-and-publish-test` — the wheel rehearsal and the image rehearsal are
  independent, and chaining them means a TestPyPI hiccup blocks the thing the
  operator actually wants to test.
- **FR-002**: Exactly ONE `docker buildx build` invocation, declaring
  `--platform linux/amd64,linux/arm64` and `--push`. Never per-arch builds
  pushing a shared tag — that silently replaces the manifest list rather than
  extending it, which is the hazard 105 already ruled on.
- **FR-003**: The pushed tag MUST derive from `github.run_id` and MUST carry the
  literal prefix `rehearsal-`. No value the job can emit may match
  `^[0-9]+\.[0-9]+\.[0-9]+$`, and the job MUST NOT reference `latest`.
- **FR-004**: GHCR login MUST use `${{ github.token }}`. `packages: write` MUST
  be declared on the **rehearsal job's own** `permissions:` block.
  `build-and-publish-test`'s block (`test-release.yml:24-28`) MUST remain
  exactly `contents: read` + `id-token: write` — an image job must not widen the
  credential the wheel job holds.
- **FR-005**: The job MUST sign the pushed digest with cosign keyless, which
  requires `id-token: write` on that job and `cosign sign --yes` for
  non-interactive use.
- **FR-006**: The job MUST run `docker buildx imagetools inspect` against the
  pushed tag and MUST exit non-zero unless both `linux/amd64` and `linux/arm64`
  appear.
- **FR-007**: The job MUST print, in one line, the elapsed build seconds and the
  job's configured `timeout-minutes`. Nobody has measured the emulated arm64
  build; this is what turns it into a number.
- **FR-008**: The `on:` block MUST remain `workflow_dispatch:` and nothing else.
  See trap T2 — widening it breaks a guard that is not in this story's test file.
- **FR-009**: The drift test MUST live in a NEW file,
  `tests/test_release_rehearsal.py`. It MUST NOT be added to
  `tests/test_release_path.py`, which US2 owns. See the contention note.
- **FR-010**: The rehearsal job MUST carry a comment naming the credential it
  uses and stating that no registry secret is stored in this repository — the
  same claim `test-release.yml:26-28` already makes about PyPI. This is a
  documentation requirement with a test: the drift test asserts the comment
  mentions `github.token`.

**US2 — the irreversible step goes last**

- **FR-011**: A preflight job MUST be added to `.github/workflows/release.yml`
  that builds the image for `linux/amd64` only and does NOT push. Its purpose is
  to fail a release before PyPI when the Dockerfile cannot build at all.
- **FR-012**: The preflight job MUST NOT declare `packages: write` and MUST NOT
  contain `--push` or a registry login. A job that proves buildability must not
  hold a credential that can publish.
- **FR-013**: `build-and-publish` (`release.yml:21`, which today declares no
  `needs:` at all) MUST declare `needs:` on the preflight job.
- **FR-014**: `build-and-publish-image` MUST continue to declare
  `needs: [build-and-publish]` (`release.yml:77`), so 105's
  `test_us1_image_job_exists_with_correct_needs` (`tests/test_release_path.py:348`)
  passes **unmodified**.
- **FR-015**: `tests/test_release_path.py:398` MUST stop accepting two answers.
  The current assertion is
  `assert ("registry: ghcr.io" in job_text or "registry: ${{ env.IMAGE_REPOSITORY }}" in job_text)`.
  It MUST assert one resolved answer.
- **FR-016**: A committed control MUST prove FR-015 goes red — the assertion
  applied to a job text whose login registry does not resolve to the GHCR host
  MUST fail.
- **FR-017**: Every test 105 landed MUST pass without modification. This story
  changes what the pipeline *orders* and what one assertion *accepts*; it does
  not change what the image job *is*.

## What already exists, and where

Read these before writing anything. All line numbers are from `6d3b3d3`.

**`.github/workflows/test-release.yml`** — 68 lines, the file US1 extends.
- `:15` `name: test-release`
- `:17-18` `on:` / `workflow_dispatch:` — **the line FR-008 protects**
- `:20-21` `jobs:` / `build-and-publish-test:`
- `:22-23` `runs-on: ubuntu-latest`, `timeout-minutes: 30`
- `:24-28` its `permissions:` block, with the comment FR-010 imitates
- Contains **zero** occurrences of `buildx`, `ghcr` or `cosign`. Verified:
  `grep -ci 'buildx\|ghcr\|cosign' .github/workflows/test-release.yml` → `0`.
  This is the whole gap.

**`.github/workflows/release.yml`** — 141 lines, the file US2 edits and the file
US1 **copies from but does not touch**.
- `:20-21` `jobs:` / `build-and-publish:` — declares no `needs:` today (FR-013)
- `:24-26` its permissions: `contents: read`, `id-token: write`
- `:76-77` `build-and-publish-image:` / `needs: [build-and-publish]` (FR-014)
- `:80-83` that job's permissions, including `packages: write`
- `:85` `IMAGE_REPOSITORY: ghcr.io/bryantharpeorg/ergane`
- `:106` `registry: ${{ env.IMAGE_REPOSITORY }}` — **correct, do not change it**,
  see T4
- `:114-119` the single buildx invocation, with `--iidfile` and `--metadata-file`
- `:122-129` cosign installer and `cosign sign --yes "${IMAGE_REPOSITORY}@${DIGEST}"`
- `:134-135` the `imagetools inspect` platform assertion

**`tests/test_release_path.py`** — the file US2 edits and US1 **must not**.
- `:25-26` `WORKFLOWS_DIR`, `RELEASE_WORKFLOW` constants
- `:254-270` `_push_is_tag_only`
- `:272-296` `_workflow_is_operator_tag_trigger_only` — **permits
  `workflow_dispatch` explicitly**, which is why FR-008 is a non-widening
  requirement rather than a redesign
- `:326-346` `_load_release_workflow`, `_job_ids`, `_image_job_text`
- `:348` `test_us1_image_job_exists_with_correct_needs` — FR-014's witness
- `:393-403` `test_us1_image_job_uses_github_token_for_ghcr_login` — **the
  assertion FR-015 tightens**
- `:473` `test_us1_image_repository_declared_once_in_workflow` — see T5
- `:520-539` `test_no_workflow_can_publish_on_branch_pr_or_merge_group` — scans
  **every** workflow file, including the one US1 edits

**`Dockerfile`** — what both the preflight and the rehearsal build. `:63-65`
carries the uid fix (`install -d`, not `useradd`) that landed in `4956123`.

**`tests/test_container_image_builds.py`** — already builds the image locally,
guarded on a reachable daemon. The rehearsal is the remote analog; this file is
the local one. Neither replaces the other and neither should be edited here.

## Technical approach, story by story

### US1 — the rehearsal pushes an image nobody depends on

Add one job to `test-release.yml`. Structurally it is `release.yml:76-141` with
three differences and nothing else:

| | release job | rehearsal job |
| --- | --- | --- |
| tag source | `GITHUB_REF_NAME` minus `v` | `rehearsal-${{ github.run_id }}` |
| `needs:` | `[build-and-publish]` | none |
| duration line | absent | required (FR-007) |

Everything else — the QEMU and Buildx setup actions, the GHCR login, the single
`--platform linux/amd64,linux/arm64 --push` invocation, `--iidfile`, the cosign
installer, `cosign sign --yes` over `repo@digest`, and the `imagetools inspect`
loop — is copied as-is. **Resist improving it while copying.** A rehearsal that
diverges from the thing it rehearses is worse than none, because it produces
evidence about a code path that will not run at release time.

Set `timeout-minutes: 90`, matching the release image job, because the emulated
`linux/arm64` cost is exactly the unknown FR-007 exists to measure.

The drift test goes in a new `tests/test_release_rehearsal.py`. It can reuse the
parsing shape of `_image_job_text` (`tests/test_release_path.py:338-346`) but
must define its own helper against `test-release.yml` rather than importing from
a file US2 is rewriting.

For FR-003, the strongest form of the test is not "the tag starts with
`rehearsal-`" but "no string the job emits as a tag matches semver". Write both:
the positive names the grammar, the negative is what actually protects the
version namespace.

### US2 — the irreversible step goes last

Two independent edits that happen to share a file.

**The reordering.** Add `build-image-preflight` to `release.yml`, before
`build-and-publish` in the file. It checks out, sets up Buildx, and runs
`docker buildx build --platform linux/amd64 --load` (or no `--platform` at all,
taking the runner's native arch) with **no** `--push` and **no** login. Then
`build-and-publish` gains `needs: [build-image-preflight]`.

Why amd64 only: the failure this catches is a Dockerfile that cannot build, and
that fails identically on both arches — `useradd -u 1000` against a base that
owns uid 1000 is not architecture-dependent. Building both platforms here would
double the emulated arm64 cost on every release to catch nothing extra.

**The assertion.** Replace the `or` at `:398`. The current comment says "either
is acceptable because the repository is declared once and referenced" — and that
reasoning is not wrong, it is simply *already enforced somewhere else*:
`test_us1_image_repository_declared_once_in_workflow` (`:473`) is what pins the
single-declaration property. So the `or` in `:398` buys nothing and costs the
pinning. Assert the resolved host, and add the FR-016 control that feeds the
assertion a job text with a wrong registry and proves it fails.

## Traps

**T1 — US1 writes a file the factory has never successfully pushed.** This is
the largest risk in the spec and it is a *landing* risk, not a *coding* risk.
`.github/workflows/*` was unpushable from the factory as recently as
2026-08-25 03:47Z: nodes push from the target repo, that clone pushed over HTTPS
with an OAuth App token, and GitHub refuses an OAuth push touching
`.github/workflows/` without the `workflow` scope
(`merge/a-story-touching-github-workflows-cannot-be-pushed-by-the-factory`). The
operator repointed the target clone's push URL to SSH — verified 2026-08-25:
`origin` fetches over HTTPS and pushes over `git@github.com:bryantharpeorg/ergane.git`
— and SSH is not subject to that scope check. **If US1's push is rejected anyway,
do not restructure the story to avoid the workflow file.** That would discard the
only evidence this run can produce. Report the rejection verbatim; the story has
done its job either way.

**T2 — do not widen the trigger, and the guard that catches it is not in your
test file.** `tests/test_release_path.py:520` scans every `*.yml` under
`.github/workflows/`, and for any file containing the word `publish`
(case-insensitive) requires `_workflow_is_operator_tag_trigger_only`. Adding a
`push:` or `pull_request:` trigger to `test-release.yml` — even briefly, even to
test it — turns that guard red in a file US1 does not own, and the failure will
read as unrelated.

**T3 — the GHCR package may not exist, and the org may forbid creating it.**
Nobody has pushed `ghcr.io/bryantharpeorg/ergane`. If the first push returns 403,
that is an **organization setting only the operator can change**, not a defect in
the job. Do not "fix" a 403 by removing the push, downgrading to a single
platform, or switching registries. Report it; that answer is worth more than a
green run.

**T4 — `registry: ${{ env.IMAGE_REPOSITORY }}` is correct. Do not "fix" it.**
It resolves to `ghcr.io/bryantharpeorg/ergane`, which looks like it should be a
bare host. Docker normalizes the path away, proven twice on 2026-08-25: both that
form and `docker login ghcr.io` contact `https://ghcr.io/v2/`, and a successful
path-form login into an isolated `DOCKER_CONFIG` stored the credential under the
key `ghcr.io` — which is the key buildx looks up at push time. Copy the line as
it is. FR-015 tightens the *test*, not the workflow.

**T5 — 105's tests are not yours to edit.** `tests/test_release_path.py` holds
fifteen tests 105 landed. FR-015 changes exactly one assertion inside
`test_us1_image_job_uses_github_token_for_ghcr_login`. Everything else in that
file, and every test in it that US1 might be tempted to extend, stays as it is.
FR-017 is checkable: run the file and confirm the count of passing tests only
goes up.

**T6 — `--iidfile` with a multi-platform `--push` writes the manifest-list
digest**, which is what cosign should sign, and that is why `release.yml:129`
signs `repo@digest` rather than `repo:tag`. Preserve that. Signing a tag rather
than a digest is a real vulnerability, not a style choice, and it is the reason
105 wrote FR-005 the way it did.

**T7 — the rehearsal leaves images behind on purpose.** Each run pushes a
multi-arch manifest under `rehearsal-<run_id>` and never deletes it. Deleting
would need `packages: delete`, a strictly larger credential than this job's
purpose justifies. Do not add a cleanup step. The `rehearsal-` prefix is the
affordance; cleanup is an operator act.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
  depends_on: []
US2:
  implements: [FR-011, FR-012, FR-013, FR-014, FR-015, FR-016, FR-017]
  depends_on: []
```

Chain depth 1. Both nodes are dispatchable in the first round.

## Sizing

Two stories, both small. US1 is one copied-and-adapted YAML job plus a new test
file — the largest risk in it is landing, not writing. US2 is one new YAML job,
one `needs:` line, one assertion and one control.

This is deliberately not a six-story spec. The unit of value the operator asked
for is "a GHCR push I can run before cutting `v0.4.0`", and that is US1 alone.
US2 is the durable fix that makes the ordering safe afterwards.

## What else is in flight, and why it does not collide

Nothing. At drafting: no epics running, no open pull requests, an empty merge
queue, and both branches converged at `6d3b3d3`.

**File contention between this spec's own two stories: none.**

| story | owns |
| --- | --- |
| US1 | `.github/workflows/test-release.yml`, `tests/test_release_rehearsal.py` (new) |
| US2 | `.github/workflows/release.yml`, `tests/test_release_path.py` |

The two sets are disjoint. They observe each other in exactly one direction:
`tests/test_release_path.py:520` (US2's file) reads
`.github/workflows/test-release.yml` (US1's file). That is why FR-008 exists. As
long as US1 leaves the `on:` block alone, either merge order is safe and no
`depends_on_merged` edge is needed.

## Dispatch hazards, for the operator running this epic

- **Do not run `scripts/gate-commit` while an attempt is in flight.** Measured
  2026-08-25: `gate-commit` creates `/tmp/ergane-gate-XXXXXX` and checks a
  worktree into it, and
  `tests/test_ergane_install_closing_step.py::test_closing_step_creates_no_schedule_no_registry_row_no_residue`
  asserts that no `/tmp/ergane-*` directory contains `specs/`. A concurrent
  operator gate therefore turns a **node's** gate red for a reason the node
  cannot see or fix. The test passes standalone (`1 passed in 0.23s`) and fails
  only inside the gate's own scratch worktree.
- **US1's landing is the experiment.** If it fails at the push step, read T1
  before concluding anything about the code.
- **Nothing here provisions the host or restarts the worker.** Both stories are
  file edits plus tests.

## Verification the operator will run, independent of the gate

The gate and the judge can only read the diff. The point of this spec is a thing
that happens on GitHub's runners, so the real verification is manual and is the
reason the spec exists:

```bash
gh workflow run test-release.yml
gh run watch                                   # read the FR-007 duration line
docker buildx imagetools inspect ghcr.io/bryantharpeorg/ergane:rehearsal-<run_id>
cosign verify ghcr.io/bryantharpeorg/ergane:rehearsal-<run_id> \
  --certificate-identity-regexp '.*' --certificate-oidc-issuer-regexp '.*'
```

Both platforms must appear in the `imagetools` output, and the recorded build
duration is the number that tells the next reader whether `timeout-minutes: 90`
is generous or tight.

**Only after that run is green should `v0.4.0` be tagged.** That ordering is the
entire purpose of this spec, and no gate can enforce it.
