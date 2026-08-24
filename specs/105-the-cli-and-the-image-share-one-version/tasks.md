# Tasks: the CLI and the image share one version

**Spec**: `specs/105-the-cli-and-the-image-share-one-version/spec.md`
**Plan**: `specs/105-the-cli-and-the-image-share-one-version/plan.md`

Read the plan's traps before the first task. Five decide whether an attempt
lands. **Trap 1**: `_skew_notice` (`factory/cli/nouns/build.py:761`) compares
git revisions off a *running epic* — it cannot be extended and must not be
touched. **Trap 2**: the identity write goes between
`factory/supervision/container_supervisor.py:256` and `:259`, never beside
`:214`. **Trap 3**: derive the identity path from the `state_home` local at
`:211-214`, never from `supervision_home()` — an env-derived path writes into
the operator's real state home during `pytest`. **Trap 4**:
`verify_controlplane` has no skip verdict (`factory/controlplane/verify.py:1118`),
so an absent identity file must return `passed=True`. **Trap 10**: nobody has
ever built this Dockerfile; US1's proof is drift tests red-then-green, never a
build log. **Trap 24**: the identity record outlives the container over a
same-path bind mount, so the supervisor removes it on exit *and* the refusal
names its path — both, or a stopped engine wedges dispatch forever.
**Trap 25**: US4 **derives** the compose project directory as
`supervision_home() / "container"`, the path spec 104 committed to; it does not
ask an operator to set a variable nothing sets.

## Phase 1: User Story 1 — The release workflow gains the image job

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-002, FR-004, FR-005) Workflow drift
      test over `.github/workflows/release.yml`, reusing
      `tests/test_release_path.py:25-26`'s `WORKFLOWS_DIR`/`RELEASE_WORKFLOW`
      and its `yaml.safe_load` shape (`:282`) rather than a fresh parser:
      assert an image job exists in **that file**; its `needs` is
      `[build-and-publish]` (the real job id at `:21`, trap 13); exactly one
      `docker buildx build` line carries `--platform` with both
      `linux/amd64` and `linux/arm64` and `--push`; GHCR login uses the
      GitHub token; a cosign step signs a **digest**, not a tag; a
      `docker buildx imagetools inspect` step fails when a platform is
      missing; the job declares `permissions: packages: write`. Red first:
      run each assertion against the unfixed file and capture it.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, FR-007) Version-source test: the
      image job's tag expression reads `GITHUB_REF_NAME` — the same value the
      existing "Validate tag against declared version" step (`:31-41`) already
      compares to `pyproject.toml:3`. One source, two consumers. And the image
      **repository** is declared exactly once in the workflow (one `env:` key);
      the login, the build tag, the cosign target and the inspect assertion all
      reference that one declaration rather than repeating a literal (trap 14).
      The test reads the repository's value out of the workflow; it must not
      restate it. US3 is the story that pins that value to the rest of the tree.
- [ ] T003 [P] [US1] (FR-006) `.dockerignore` drift test: the file exists;
      `.git`, `.venv`, `.factory`, `.claude`, `dist`, `build`,
      `**/__pycache__` and `*.egg-info` are excluded; `pyproject.toml`,
      `README.md`, `personas.example.yaml` and `factory/` are **not** — the
      wheel's `readme` (`pyproject.toml:5`) and its force-include (`:67-68`)
      need the last two (traps 7, 8).
- [ ] T004 [P] [US1] (FR-004) Permissions-containment test: the
      `build-and-publish` job's `permissions:` block is still exactly
      `contents: read` + `id-token: write` (`:24-26`), and
      `tests/test_release_path.py:319`
      (`test_no_workflow_can_publish_on_branch_pr_or_merge_group`) still
      passes unmodified (trap 12).

### Implementation for this story

- [ ] T005 [US1] (FR-006) Write `.dockerignore` at the repo root per T003. This
      is a **prerequisite of the first build, not tidiness**: `Dockerfile:44`
      is `COPY . /opt/ergane` and `:46` runs `python3 -m venv .venv` over the
      copied tree without `--clear`, and this host's `.venv/pyvenv.cfg` names
      an aarch64 CPython 3.13 (trap 8).
- [ ] T006 [US1] (FR-001..FR-005) Add the image job to
      `.github/workflows/release.yml`: `needs: [build-and-publish]`, its own
      `timeout-minutes: 90` (trap 11 — do not raise `:23`, do not add a
      `matrix:` to that job), its own `permissions:` block with
      `contents: read` + `id-token: write` + `packages: write`, QEMU + buildx
      setup, GHCR login with the GitHub token, **one**
      `docker buildx build --platform linux/amd64,linux/arm64 --push` writing a
      metadata/iid file, `cosign sign --yes <repo>@<digest>`, and an
      `imagetools inspect` assertion that exits nonzero unless both platforms
      appear. Tag = `${GITHUB_REF_NAME#v}` (FR-003).

### Verification for this story

- [ ] T007 [US1] (spec US1-S1, spec US1-S2, SC-001) Paste the drift suite
      red-then-green, **one paste per assertion group, not per assertion** —
      seven, matching the landed precedent at `specs/088…/tasks.md:131-132`:
      (1) the job and its `needs`, (2) the single two-platform buildx line,
      (3) the GHCR login, (4) the cosign digest step, (5) the imagetools
      platform assertion, (6) the new job's `packages: write` plus
      `build-and-publish`'s unchanged block, (7) `.dockerignore`'s excludes and
      must-not-excludes as one group. Nineteen separate mutation runs buys the
      judge nothing it can check — it sees the diff and the criteria only — and
      costs attempt time, so do not enumerate them. State in the commit message
      that the 0.4.0 release cut is the operator's verification step
      (`docs/container-onramp-program.md:131`) and that no build was run
      (trap 10).

## Phase 2: User Story 2 — The engine writes its identity

### Tests for this story (write FIRST, must fail)

- [ ] T008 [US2] (spec US2-S1, FR-010) Drive `_run_supervisor`
      (`factory/supervision/container_supervisor.py:197`) with the existing
      stub harness (`tests/test_container_supervisor.py:42 supervisor_mod`,
      `:94 make_child`, `:108 config`): when `start_child("worker", …)` is
      called, the identity file already exists and parses. Assert the ordering
      from the stub's own call log, not from a sleep.
- [ ] T009 [P] [US2] (spec US2-S1, FR-010) The negative half: when
      `probe_address` never answers and `_run_supervisor` returns 1 at `:256`,
      **no identity file is written**. An engine that never came up must not
      advertise identity (trap 2).
- [ ] T009a [P] [US2] (spec US2-S3, FR-021) **The record's lifetime.** Drive
      `_run_supervisor` through a full startup and then a shutdown on the same
      stub harness (a child exiting, and separately a `SIGTERM`-shaped shutdown
      via the stub controllers): the identity file exists while the children are
      up and is **gone** once `_run_supervisor` returns. Assert the return code
      is unchanged by the removal — the exit status is the fault report and the
      unlink may not edit it — and that a second run over a `state_home` whose
      record was already deleted by hand still returns normally
      (`missing_ok`). The record lives on the host side of a same-path bind
      mount (`container/compose.reference.yaml:21`, `:25`, `HOME` at `:34`), so
      without this a stopped engine keeps refusing dispatch forever (trap 24).
- [ ] T010 [P] [US2] (spec US2-S1, FR-010) Isolation test: with the `config`
      fixture's tmp `state_home` and `HOME` **left alone**, the file lands
      under the tmp path and nothing is created under the real
      `~/.local/state/ergane/supervision`. Also assert
      `identity_path(resolve_state_home()) == supervision_home() /
      IDENTITY_FILENAME` so the two joins are pinned together without the
      supervisor calling the env-only resolver (trap 3).
- [ ] T011 [P] [US2] (spec US2-S2, FR-011) Restart test: run the supervisor
      twice against the same `state_home` with different versions; the file is
      **replaced whole**, is valid JSON on the second read, and contains
      exactly one record. Assert the write is atomic (temp file + rename), so
      a concurrent reader never sees a partial document.
- [ ] T012 [P] [US2] (spec US2-S2, FR-011) Record test: `version`,
      `started_at` (UTC, ISO-8601, parseable), `image_reference` populated from
      `ERGANE_VERSION` when set and `null` when unset, `image_digest` populated
      from `ERGANE_IMAGE_DIGEST` when set and `null` otherwise. Assert `null`
      is the default for both — a digest is not knowable at build time
      (trap 17).
- [ ] T013 [P] [US2] (FR-008, FR-009) Vocabulary tests: `IMAGE_REPOSITORY`
      equals the repository parsed out of `container/compose.reference.yaml:10`
      (trap 14); `image_reference("1.2.3")` is that repository plus `:1.2.3`;
      `cli_version()` returns `importlib.metadata.version("ergane-cli")` and
      `"unknown"` when the distribution is absent; the module imports nothing
      outside the standard library.
- [ ] T014 [P] [US2] (FR-009) `factory/cli/main.py`'s `_version_text()` calls
      `cli_version()` and no longer holds its own `importlib.metadata` call
      (trap 18) — and the existing `ergane --version` tests pass **unmodified**.

### Implementation for this story

- [ ] T015 [US2] (FR-008, FR-011) Create
      `factory/supervision/engine_identity.py`: `IDENTITY_FILENAME`,
      `IMAGE_REPOSITORY`, `cli_version()`, `image_reference(version)`,
      `identity_path(state_home)`, frozen `EngineIdentity`,
      `write_identity` (temp file + `os.replace`), `read_identity` returning
      `None` when absent or unparseable. Standard library only — the host CLI
      imports this on the `build start` path.
- [ ] T016 [US2] (FR-010) In `_run_supervisor`, write the identity **between
      `:256` and `:259`** — after the readiness branch can no longer be
      reached, before the worker child starts — using the `state_home` local
      already resolved at `:211-214` (traps 2, 3).
- [ ] T016a [US2] (spec US2-S3, FR-021) Remove the identity file in
      `_run_supervisor`'s `finally` block
      (`factory/supervision/container_supervisor.py:333-335`, which today only
      removes the two signal handlers). That `finally` belongs to the `try:` at
      `:298`, entered strictly after the write at trap 2's insertion point, so
      every path that created the record runs it. Best-effort: `missing_ok`, no
      exception escaping, and nothing below it in the function touched — the
      return values at `:345` and `:355` are the fault report.
- [ ] T017 [US2] (FR-009) Rewire `factory/cli/main.py:131-135` to
      `cli_version()`. The printed string does not change.

### Verification for this story

- [ ] T018 [US2] (spec US2-S1, spec US2-S2, spec US2-S3, SC-002) Paste the
      identity file from a stub supervisor run; the same path after a restart at
      a different version showing replacement not append; the absent-file result
      of the readiness-timeout run; the directory listing after a completed run
      showing the record removed, beside the return code that run produced
      (FR-021); and the isolation assertion's output.

## Phase 3: User Story 3 — The handshake refuses

### Tests for this story (write FIRST, must fail)

- [ ] T019 [US3] (spec US3-S1, spec US3-S3, FR-012, FR-022) The comparison,
      three branches: mismatch returns one sentence naming **both** versions,
      the `docker pull ghcr.io/bryantharpeorg/ergane:<cli>` command,
      `ergane engine upgrade` (trap 15), **and the absolute path of the identity
      record** — assert the path appears in the sentence, and that it is the
      same value `identity_path(resolve_state_home())` returns under a
      `tmp_path` `ERGANE_STATE_HOME`, not an abbreviation or a `~`. That fourth
      element is the only remedy that works when the engine is gone rather than
      stale, which is the wedge trap 24 describes. Equal versions return `None`;
      a missing identity file returns `None` (trap 16 — the wording is fixed
      here and US4 must spell the verb identically).
- [ ] T020 [P] [US3] (spec US3-S1, FR-013) `factory/cli/nouns/build.py`: with a
      mismatched identity file, `_run_preflight` (`:316`) yields a
      `factory.workgraph.preflight.PreflightFinding` with `check="engine"`,
      `passed=False`, `transport=False`; the refusal loop (`:684-695`) prints
      `ergane: preflight [engine]: …` on stderr and the command returns
      `EXIT_USER` (`:335`). Name the finding type explicitly (trap 6).
- [ ] T021 [P] [US3] (spec US3-S1, FR-013) The **second** site:
      `factory/workgraph/cli.py:119 _run_preflight` refuses identically. Assert
      it directly — `tests/test_landing_dials_reach_the_epic.py:700-728` exists
      because this site is a live door onto the same workflow (trap 5).
- [ ] T022 [P] [US3] (spec US3-S2, FR-014) The `install --verify` probe: a
      mismatched identity file yields a
      `factory.mergequeue.models.Finding` with `check="engine"`,
      `passed=False` and the same sentence; a matching one yields
      `passed=True`.
- [ ] T023 [P] [US3] (spec US3-S3, FR-014) **The absent case, which is most of
      the world.** With no identity file anywhere, the probe returns
      `passed=True` with a detail naming the path it looked at and saying the
      check activates on evidence. Assert `verify_controlplane`'s exit code is
      unchanged on a host with no identity file — there is no skip verdict
      (`factory/controlplane/verify.py:1118`, trap 4).
- [ ] T024 [P] [US3] (spec US3-S2, FR-015) `ergane status`: a mismatch appends
      one string to `FloorStatus.notes` (`factory/cli/status.py:263`, appended
      near `:294`, **above** the `_open_client` call at `:299` so the note
      survives a Temporal outage), rendered as `note: …` (`:728`) and present in
      `--json` via `asdict(floor)` (`:274`). No new dataclass field. No test
      drives `collect_floor` today, so build the harness the cheap way rather
      than inventing one: `collect_floor` imports `_open_client` inside the
      function at `:299` and that seam exists to be patched
      (`factory/cli/nouns/__init__.py:42`). Patch it to raise `OperatorError`,
      point `specs_root` at a `tmp_path`, and `asyncio.run(collect_floor(...))`
      answers with no server anywhere; `degraded=True` from the absent client is
      expected and is not what you are asserting.
- [ ] T025 [P] [US3] (spec US3-S1, FR-012) **One repository string, three
      artifacts.** The remedy sentence names an image reference, and it has to
      be the image CI actually publishes. Assert that the repository declared
      once in `.github/workflows/release.yml`'s image job, the repository in
      `container/compose.reference.yaml:10` (split at `:${`), and
      `IMAGE_REPOSITORY` are the same string — derived from all three files,
      never restated as a literal (trap 14). This assertion lives here rather
      than in US1 or US2 because it is the handshake's own claim: the tag the
      refusal tells an operator to pull must be the tag the release pushed.
- [ ] T026 [P] [US3] (spec US3-S2) The native path is untouched:
      `tests/test_ergane_build_status_refusal.py` passes **unmodified**, and
      `_cli_revision` (`factory/cli/nouns/build.py:741`), `_skew_notice`
      (`:761`) and `factory/cli/nouns/__init__.py:37` are byte-identical in the
      diff (trap 1). Assert this as a diff-level claim in the paste, not as a
      code assertion.

### Implementation for this story

- [ ] T027 [US3] (FR-012) Add the comparison to
      `factory/supervision/engine_identity.py` — one function, the only place
      the refusal wording lives, so the three surfaces cannot drift.
- [ ] T028 [US3] (FR-013) Add `engine_skew_findings(...)` to
      `factory/workgraph/preflight.py` returning `PreflightFinding`
      (`:100`), and call it from **both** `factory/cli/nouns/build.py:316` and
      `factory/workgraph/cli.py:119` (trap 5). Do **not** add it to
      `factory/activities/roadmap_activities.py:390` — the roadmap runs inside
      the engine, so there is no host CLI to be skewed from; say so in a
      comment where a future reader would otherwise think it was forgotten.
- [ ] T029 [US3] (FR-014) One probe class in `factory/controlplane/verify.py`
      beside `ForgeCapabilityProbe` (`:1024`), registered in `REGISTRY`
      (`:1081`). Its docstring makes the same argument `:1034-1041` makes: a
      first-run version defect belongs in `install --verify`, not the doctor,
      because it is true before any epic exists.
- [ ] T030 [US3] (FR-015) One `notes.append(...)` in `collect_floor`.
- [ ] T031 [US3] (FR-016) Edit `docs/container.md:73-75` so the landed doc
      states the remedy this spec prints — both the `docker pull` command and
      `ergane engine upgrade` (trap 15). Touch nothing else in that file; US4
      appends below.

### Verification for this story

- [ ] T032 [US3] (spec US3-S1, spec US3-S2, spec US3-S3, SC-003) Paste: the
      refusal at both dispatch sites with both version strings **and the
      identity record's path** visible in the printed sentence (FR-022); the
      probe's three verdicts (mismatch, match, absent) with the absent one
      green; the `ergane status` note in text and in `--json`; and the
      unmodified native-path test file passing.

## Phase 4: User Story 4 — The upgrade verb drains first

### Tests for this story (write FIRST, must fail)

- [ ] T033 [US4] (spec US4-S1, FR-018) With open epics injected through the
      seam, `ergane engine upgrade` refuses **naming them** and what stopping
      now would cost, exits nonzero, and calls no stop/start on the docker
      seam. Model the wording on `factory/supervision/units.py:791-797` and
      `:894-905` — the shape, not the words (trap 20).
- [ ] T034 [P] [US4] (spec US4-S1, FR-018) `--force` proceeds through the same
      refusal, and the report records that it was forced.
- [ ] T035 [P] [US4] (spec US4-S2, FR-019, FR-020) The drained path, asserted
      as an **ordered** seam call log: stop, start with
      `image_reference(cli_version())`, verify-through, then retention. No test
      runs `docker` (trap 21).
- [ ] T036 [P] [US4] (spec US4-S2, FR-019) Retention: with images for the new,
      the previous and two older versions present, exactly the older two are
      removed. Never the current, never the immediately previous — and when
      the running version cannot be read from the identity file, **nothing** is
      removed: unknown is not zero
      (`factory/supervision/deploy.py:168-202`, trap 19).
- [ ] T037 [P] [US4] (spec US4-S2, FR-019) Verify-through is real, and
      **`degraded` is keyed on the engine finding alone**: with the verify seam
      returning US3's `check="engine"` finding as a mismatch, the upgrade reports
      degraded; with the engine finding green but an *unrelated* probe red (the
      LLM proxy, `gh` capability — `verify_controlplane` runs all seven in
      `factory/controlplane/verify.py:1081-1089` and collapses them to one exit
      code at `:1118`), the upgrade reports **success** and still carries every
      finding in the report for the operator to read. Assert both directions;
      the second is the one that stops a working upgrade from being called a
      failure by something it did not touch.
- [ ] T038 [P] [US4] (spec US4-S3, FR-017, FR-023) The project directory is
      **derived, then checked** — never guessed and never demanded from an
      operator. With `ERGANE_STATE_HOME` pointed at a `tmp_path` containing no
      `ergane/supervision/container/compose.yaml`, the verb refuses naming the
      directory it looked in and `ergane install` as what creates it, exits
      nonzero, and calls nothing on the docker seam. Assert the resolved
      directory equals `supervision_home() / "container"` — 104's committed
      record (`specs/104…/plan.md`'s ruling **R1**) — and that an
      `ERGANE_COMPOSE_PROJECT` override, when set, wins. Assert the refusal does
      **not** instruct the operator to set that variable: nothing sets it, 104's
      ruling **R2** says there is no saved declaration to honour, and
      a refusal that demands an unset variable is a support round trip (trap 25).
      Third branch: a directory that exists but holds no `compose.yaml` refuses
      the same way.

### Implementation for this story

- [ ] T039 [US4] (FR-018, FR-019, FR-020, FR-023) `factory/supervision/engine_upgrade.py`:
      the open-epic read via `factory/supervision/units.py:996 _open_epics` /
      `factory/versioning.py:171 open_epic_from`; the drain refusal; the project
      directory resolved as `supervision_home() / "container"`
      (`factory/supervision/units.py:245`) with `ERGANE_COMPOSE_PROJECT` honoured
      as an override, and refused when that directory or its `compose.yaml` is
      absent — **do not import `factory/supervision/container_project.py`**, it
      does not exist until 104 lands; leave a comment naming 104's
      `installed_project(layout)` as the later delegation (trap 25); one
      injectable docker seam (`stop`, `start(image_reference)`, `verify`,
      `list_images`, `remove_image`) defaulted to a `docker compose` runner
      against that directory; the retention decision as a **pure
      function** so its two negative properties are returned values, exactly
      as `deploy.py:168-202` does it; a report dataclass carrying `degraded`,
      set from the `check="engine"` finding alone (FR-019).
      Export `ERGANE_VERSION=cli_version()` when starting the engine — nothing
      in the tree produces that variable today and
      `container/compose.reference.yaml:10` substitutes it (trap 9).
- [ ] T040 [US4] (FR-017) `factory/cli/nouns/engine.py`: a thin noun on the
      template of `factory/cli/nouns/worker.py` — parser, `upgrade` verb with
      `--force`, exit code from `report.degraded`. No dispatcher edit is needed;
      discovery is `pkgutil.iter_modules` (`factory/cli/main.py:53-96`).
- [ ] T041 [US4] (FR-017) Append a new "Upgrading the engine" section at the
      **end** of `docs/container.md`: the drain rule, `--force` and what it
      costs, and the one-release retention. Edit nothing above it — US3 owns
      `:73-75` (trap 15).

### Verification for this story

- [ ] T042 [US4] (spec US4-S1, spec US4-S2, spec US4-S3, SC-004) Paste: the
      in-flight refusal naming the open epics; the no-project refusal naming the
      derived directory and `ergane install` (FR-023); the `--force` path
      proceeding; the drained path's ordered seam call log; the retention
      decision over four versions including the unknown-is-not-zero branch; and
      both `degraded` directions from T037. Every one of these is a **seam
      capture through the injected runner**, captured in a test, not a
      real-daemon run: no attempt has a docker socket, and trap 21 forbids one.
      Say so in the commit message and name the operator's real-hardware list
      (`plan.md`'s "Verification the operator will run") as where the daemon
      half lives.
