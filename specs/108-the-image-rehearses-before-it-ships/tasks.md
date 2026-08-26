# Tasks: the image rehearses before it ships

**Spec**: `specs/108-the-image-rehearses-before-it-ships/spec.md`
**Plan**: `specs/108-the-image-rehearses-before-it-ships/plan.md` — read its
**Traps** section before writing anything. T1, T4 and T8 in particular will each
cost an attempt if discovered rather than read.

`[P]` marks a task that may run in parallel with its siblings — different file,
no ordering dependency. Every task cites the spec scenario and the FR numbers it
discharges, so the judge can check it against criteria provable from the diff.

Tests are written **first and must fail** before the implementation task in the
same phase. A test that passes before the implementation exists is measuring
nothing, and this spec exists precisely because a suite full of such tests let a
Dockerfile that could not build reach 25 landed stories.

---

## Phase 1: User Story 1 — The rehearsal pushes an image nobody depends on

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-002, FR-004, FR-005, FR-006) Create
  `tests/test_release_rehearsal.py` with a drift test over
  `.github/workflows/test-release.yml`. Define a local `_rehearsal_job_text()`
  helper — model it on `tests/test_release_path.py:338-346` but **do not import
  from that file**, which US2 is rewriting (plan FR-009, contention note).
  Assert the rehearsal job declares: exactly one `docker buildx build`
  invocation; `--platform linux/amd64,linux/arm64` and `--push` on that
  invocation; `registry:` resolving to the GHCR host; `password: ${{ github.token }}`;
  `packages: write` in the job's own `permissions:` block;
  `uses: sigstore/cosign-installer@v3`; exactly one `cosign sign` line, targeting
  `repo@digest` and not `repo:tag`; and a `docker buildx imagetools inspect` step
  naming both platforms with a reachable `exit 1`. Must be **red** now — the job
  does not exist.

- [ ] T002 [P] [US1] (spec US1-S2, FR-003) Tag-grammar test, in two halves. The
  positive: the pushed tag derives from `github.run_id` and carries the literal
  prefix `rehearsal-`. The negative, which is the one that matters: **no** string
  the job emits as a tag matches `^[0-9]+\.[0-9]+\.[0-9]+$`, and the job text
  contains no reference to `latest`. The negative protects the version namespace
  from a future edit that points the rehearsal at a real tag; the positive only
  documents today's shape.

- [ ] T003 [P] [US1] (spec US1-S1, FR-004) Permissions-containment test: assert
  `build-and-publish-test`'s `permissions:` block (`test-release.yml:24-28`) is
  still exactly `contents: read` + `id-token: write`, with **no**
  `packages: write`. Adding an image job must not widen the credential the wheel
  rehearsal holds. Red only if someone hoists permissions to workflow level.

- [ ] T004 [P] [US1] (spec US1-S3, FR-008) Trigger non-widening test: assert
  `test-release.yml`'s `on:` block contains `workflow_dispatch` and **nothing
  else** — no `push`, no `pull_request`, no `merge_group`. This duplicates part
  of what `tests/test_release_path.py:520` enforces globally, deliberately: the
  global guard lives in a file this story does not own, and a local test names
  the constraint where the person editing the file will see it. See plan trap T2.

- [ ] T005 [P] [US1] (spec US1-S5, FR-010) Credential-documentation test: assert
  the rehearsal job carries a comment mentioning `github.token` and stating that
  no registry secret is stored in this repository. Model the wording on
  `test-release.yml:26-28`, which makes the same claim about PyPI.

- [ ] T006 [P] [US1] (spec US1-S6, spec US1-S7, FR-018, FR-019, FR-020)
  Package read-back test, in three parts. **Linkage**: the job contains a step
  that reads the package from the GitHub API and compares its linked repository
  against `github.repository`, with a reachable non-zero exit. **Visibility**:
  the same step compares visibility against the literal `public`, with its own
  reachable non-zero exit — two separate failures, because "wrong owner" and
  "private" have different remedies and a combined assertion hides which one
  fired. **No second literal**: assert the job text contains no hardcoded
  `bryantharpeorg` or `ergane` outside the single `IMAGE_REPOSITORY` declaration,
  which is FR-020 and is what keeps
  `test_us1_image_repository_declared_once_in_workflow` green. Red now — no such
  step exists.

### Implementation for this story

- [ ] T007 [US1] (FR-001..FR-008, FR-010) Add the rehearsal job to
  `.github/workflows/test-release.yml`, turning T001–T005 green. Copy
  `.github/workflows/release.yml:76-141` and change exactly three things: the tag
  becomes `rehearsal-${{ github.run_id }}`; there is no `needs:`; and the build
  step is wrapped to emit the FR-007 duration line. **Copy the rest verbatim** —
  the QEMU and Buildx setup actions, the login, the single `--platform
  linux/amd64,linux/arm64 --push` invocation, `--iidfile`, the cosign installer,
  `cosign sign --yes` over `repo@digest`, and the `imagetools inspect` loop.
  Plan trap T4: `registry: ${{ env.IMAGE_REPOSITORY }}` is **correct**; copy it
  unchanged. Set `timeout-minutes: 90`, matching the release image job. Do not
  touch the `on:` block.

- [ ] T008 [US1] (spec US1-S4, FR-007) Add the duration report to the build step: capture a
  start timestamp, and after the build print one line carrying the elapsed
  seconds and the job's configured `timeout-minutes`. This is the only number
  anyone has about the emulated `linux/arm64` cost, and it is why the operator
  reads the run at all.

- [ ] T009 [US1] (spec US1-S6, spec US1-S7, FR-018, FR-019, FR-020) Add the
  package read-back step, turning T006 green. It goes **after** the `imagetools`
  assertion — on the first run the package does not exist until the push creates
  it, so a read-back placed earlier asserts against a 404. Derive the org and
  package name from `IMAGE_REPOSITORY` and `github.repository_owner` rather than
  writing either literal again (FR-020); the plan's US1 section carries the exact
  shell. Both failure messages must print what was **observed**, not only what
  was expected, and the visibility failure must name the package settings page as
  its remedy. Read plan trap T8 first: the invariant this step protects is that
  the package is created by the first Actions push and by nothing else.

### Verification for this story

- [ ] T010 [US1] (spec US1-S1, spec US1-S2, spec US1-S3, spec US1-S4, spec US1-S6,
  spec US1-S7, SC-001) Paste, in the PR body, the
  `tests/test_release_rehearsal.py` suite **red before T007 and green after**,
  and the red-first control for each required element: remove `--push`, then the
  cosign step, then one platform from `--platform`, then the `imagetools`
  assertion, then the linkage comparison, then the visibility comparison — each
  in turn — and paste the failing test name for each. A drift test that has never
  been observed failing is not evidence that it drifts red. Also paste
  `tests/test_release_path.py::test_no_workflow_can_publish_on_branch_pr_or_merge_group`
  and `::test_us1_image_repository_declared_once_in_workflow` passing
  **unmodified** — the first is spec US1-S3, the second is what FR-020 must not
  break.

---

## Phase 2: User Story 2 — The irreversible step goes last

### Tests for this story (write FIRST, must fail)

- [ ] T011 [US2] (spec US2-S1, FR-011, FR-013) Ordering test over
  `.github/workflows/release.yml`: a preflight job exists; it declares a
  `docker buildx build` for `linux/amd64` with **no** `--push`; and
  `build-and-publish` declares `needs:` on it. `build-and-publish` declares no
  `needs:` today (`release.yml:21-26`), so this is red now.

- [ ] T012 [P] [US2] (spec US2-S2, FR-012) Preflight credential-floor test: the
  preflight job declares **no** `packages: write`, contains no `--push`, and
  contains no registry login step. A job whose only purpose is proving
  buildability must not hold a credential that can publish.

- [ ] T013 [P] [US2] (spec US2-S1, FR-014) Regression guard: assert
  `build-and-publish-image` still declares `needs: [build-and-publish]`. This is
  what keeps 105's `test_us1_image_job_exists_with_correct_needs`
  (`tests/test_release_path.py:348`) green, and it is stated here as its own task
  so that inserting a preflight cannot silently re-parent the image job.

- [ ] T014 [P] [US2] (spec US2-S3, FR-016) The red-first control for FR-015:
  feed the tightened GHCR-login assertion a job text whose `registry:` does not
  resolve to the GHCR host, and prove it **fails**. Write this before T015.
  Without it, FR-015 is an assertion nobody has watched go red — which is the
  same class of defect FR-015 is fixing.

### Implementation for this story

- [ ] T015 [US2] (FR-015) Tighten
  `tests/test_release_path.py:393-403`. Replace
  `assert ("registry: ghcr.io" in job_text or "registry: ${{ env.IMAGE_REPOSITORY }}" in job_text)`
  with an assertion on one resolved answer, and delete the now-false comment at
  `:396-397` ("either is acceptable"). Its reasoning — that the repository is
  declared once and referenced — is already enforced by
  `test_us1_image_repository_declared_once_in_workflow` (`:473`), so the `or`
  buys nothing and costs the pinning. **This is the only assertion in this file
  you may change** (plan trap T5).

- [ ] T016 [US2] (FR-011, FR-012, FR-013) Add the preflight job to
  `release.yml`, placed before `build-and-publish` in the file, and add
  `needs:` to `build-and-publish`. The preflight checks out, sets up Buildx, and
  builds for the runner's native arch with no push and no login. Turns
  T011–T013 green. Do not touch `build-and-publish-image` (FR-014).

### Verification for this story

- [ ] T017 [US2] (spec US2-S3, spec US2-S4, SC-002) Paste the FR-016 control
  red-then-green, and paste the **full** `tests/test_release_path.py` run showing
  every test 105 landed still passing — with the before and after counts, so
  FR-017 is checkable rather than asserted. The count of passing tests may only
  go up.

- [ ] T018 [US2] (spec US2-S1) Paste the resolved job graph of `release.yml`
  after the change — the three job ids with their `needs:` — showing that nothing
  irreversible runs before the image has been proven buildable. This is the whole
  claim of the story and it should be readable in four lines.

---

## What no task here can prove

Every task above is checkable from the diff, which is the constitution's
requirement and the judge's only input. **None of them proves the thing the spec
is for.** A GHCR push, an emulated arm64 build, a cosign keyless signature and a
package's linkage all happen on GitHub's runners, and no committed test reaches
them. T006 and T009 assert that the job *contains* the read-back; only a run
proves what the read-back *says*.

The operator verification in `plan.md` is therefore not optional garnish — it is
the acceptance test, and it runs after this epic lands:

```bash
gh workflow run test-release.yml
```

If that run is red for an environmental reason — a 403 on the push, or a package
that comes back private — that is a **result**, not a failure of this epic. See
plan traps T3 and T8. Producing those answers cheaply, under a tag nothing
depends on, is the entire point.
