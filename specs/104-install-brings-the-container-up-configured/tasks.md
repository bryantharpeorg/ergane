# Tasks: install brings the container up configured

**Spec**: `specs/104-install-brings-the-container-up-configured/spec.md`
**Plan**: `specs/104-install-brings-the-container-up-configured/plan.md`

Read the plan's rulings and traps before the first task. These decide whether an
attempt lands.

- **R1/R2**: nothing about the engine backend goes into `config.toml` — the
  parser refuses unknown top-level keys by name. The record is the generated
  project on disk.
- **R4**: the reference-agreement test is **structural** — parsed YAML plus the
  ordered comment lines — never byte equality, and the comments are *data on
  the project*, not literals in the renderer. A renderer that hard-codes the
  reference's header emits "this is a reference artifact" into the operational
  `compose.yaml`.
- **R6**: the engine's Temporal database is `<state root>/temporal/engine.db`.
  It is covered by the **state-root** mount, not the supervision-home mount,
  and it is deliberately *not* the native tier's `dev.db`
  (`factory/supervision/units.py:500` writes that one).
- **R10**: `container/seccomp-ergane.json` and `container/ergane-engine.profile`
  become package data; `Dockerfile` cannot, so the local-build path refuses by
  name when the install root holds no `Dockerfile`.
- **R12**: one Temporal address convention, `host:port`, on both sides — and the
  supervisor is fixed to honour it rather than appending a second port.
- **Trap 1**: the engine question lives *outside* `_interview`, in a step called
  from `install_command`, or a 15-entry positional answer list moves under
  **five** test modules — one of which indexes it by literal position.
- **Trap 3**: the engine container must be handed its config and persona
  registry by explicit path, or every persona silently resolves to an `example/`
  alias and the engine starts clean.
- **Trap 6**: the host's `127.0.0.1:7233` is already held by the native
  Temporal. Probe the published port before `compose up`, or the CLI ends up
  talking to a different server than the engine.
- **Trap 7**: the AppArmor prompt defaults to **yes**, inverting the only
  consent precedent in this repository. That inversion is approved; write the
  reasoning into the comment.
- **Trap 11**: no test starts a Docker daemon, a container or `apparmor_parser`.
  Every process goes through an injected runner seam.

**Every transcript below is a seam capture** (trap 14). The agent sandbox binds
no Docker socket (`factory/workgraph/adapter.py:477-524`), there is no daemon,
no network and no `apparmor_parser` — so a transcript file that reads like a
real run is not evidence, it is fiction a diff-only judge cannot distinguish
from evidence. Each verification task below commits its transcript *and* states
in the file's first lines that it was captured through the named injected
seams. The real-hardware runs are the operator's, listed at the end of
`plan.md`, and no criterion here depends on one.

## Phase 1: User Story 1 — The interview asks where the engine runs

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1) In `tests/test_install_engine_question.py`,
      drive `install_command` through an injected prompter with the Docker
      probe stubbed to "a daemon answers": assert the engine question is asked,
      that `container` is offered first with `systemd` and `none` both present
      in the choices string, and that answering `systemd` or `none` leaves the
      written `config.toml` byte-identical to today's for the same answers.
- [ ] T002 [P] [US1] (spec US1-S2) Docker probe stubbed to "no daemon": choosing
      `container` raises `OperatorError` naming the daemon as missing and how to
      get it. Assert the refusal also distinguishes the legacy-binary case —
      `docker-compose` present but `docker compose` absent — by name, per the
      spec's Assumptions.
- [ ] T003 [P] [US1] (spec US1-S3) `--non-interactive` and `--from-file` resolve
      the backend to `none` and ask nothing: assert through `_FilePrompter` that
      the answer list they consume is unchanged in length and order, and that
      the **five** modules that reach `GATEWAY_ANSWERS` are untouched by this
      change — `tests/test_ergane_install_walkthrough.py` (which defines it and
      indexes it by literal position at `:568` and `:660`),
      `tests/test_install_mode_routing.py`,
      `tests/test_direct_mode_refused.py`,
      `tests/test_controlplane_direct_mode.py` (which import it) and
      `tests/test_us2_shipped_registry.py:100` (which duplicates it wholesale).
- [ ] T004 [P] [US1] (spec US1-S1, US1-S3) `--engine=container|systemd|none` on
      the install noun skips the question and takes the same refusal path when
      the daemon is missing; the flag's absence still asks. Assert that
      `--engine` combined with `--non-interactive` or with `--from-file` is
      **refused by name** — those two paths return before any engine step could
      run (`factory/cli/install.py:692`, `:696`), so honouring the flag is
      impossible and ignoring it silently discards an explicit operator
      instruction.

### Implementation for this story

- [ ] T005 [US1] (spec US1-S1, US1-S2) In `factory/cli/install.py`, add
      `_docker_daemon_available()` immediately beside
      `_systemd_user_session_available` (`:1256`) — one bounded, `check=False`
      subprocess through the same discipline, catching `TimeoutExpired`/`OSError`
      — plus `_offered_engine_backend(...)` shaped on `_offered_llm_mode`
      (`:1602`) and its `_OfferedLLM` carrier (`:1578-1582`), returning the
      offered backend, the choices string and an `unavailable_reason`. The
      predicate is about the **daemon only**: per R10 the "can this installation
      build an image" question belongs to the generator, and a second copy of it
      here is how two capability probes stop agreeing.
- [ ] T006 [US1] (spec US1-S1, US1-S3) Add `_interview_engine(prompter)`
      modelled on `_interview_personas` (`:516`) — a step called from
      `install_command` (`:687`) with an injected prompter, **never** from
      `_interview` (`:1125`, trap 1) — asking through `_ask` (`:1391`) and
      returning the choice as a value. Per R2 it persists nothing and reads no
      disk state; per R3 the call site is *before* the `_interview_personas`
      call at `:717`, so the interview asks everything before it does anything.
      On `container`, print the chosen backend; that print is what US5 replaces.
- [ ] T007 [US1] (spec US1-S2, US1-S3) Guard the chosen backend exactly as
      `_ask_temporal` guards managed mode (`:1288-1294`): a `container` choice
      with no daemon raises `OperatorError` naming the missing piece. Add
      `--engine` to `factory/cli/nouns/install.py:119` beside `--verify`
      (`:130`) and teach the `_run` ladder (`:153`) nothing new — the flag is
      read inside `install_command`, which is also where the
      `--engine` + `--non-interactive` / `--from-file` refusal of T004 lives,
      before the early returns at `:692` and `:696`.

### Verification for this story

- [ ] T008 [US1] (spec US1-S1, US1-S2, US1-S3) Commit
      `docs/104-us1-engine-question-transcript.md`, headed by one paragraph
      naming it a **seam capture** and listing the seams it ran through (the
      injected prompter and the stubbed Docker predicate — no daemon was
      contacted). It holds, as pasted output: the offered-question capture with
      the probe stubbed present, the refusal capture with it stubbed absent, the
      `--non-interactive` capture showing no engine question, the `--engine`
      combination refusal, and the pasted `pytest` summary line for the five
      answer-list modules named in T003 showing them green and unmodified.

## Phase 2: User Story 2 — The generator emits the compose project

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US2] (spec US2-S3) In `tests/test_container_project.py`, assert the
      **structural** agreement R4 rules: `yaml.safe_load(render(reference_project()))`
      equals `yaml.safe_load` of `container/compose.reference.yaml`, and the
      ordered tuple of comment lines (every line whose first non-space character
      is `#`) is equal on both sides. Red first: the renderer does not exist.
      **Do not assert byte equality** — the committed file mixes flow and block
      style, quotes `user` but not `init`, and carries
      `${ERGANE_REPO_EXAMPLE:-/path/to/repo}` interpolation; R4 explains why
      pinning that is a museum rather than a test. **Do not edit
      `container/compose.reference.yaml`**: this story changes no committed byte
      of it.
- [ ] T010 [P] [US2] (spec US2-S3) R4's comment model: assert `header` and
      `annotations` are fields on the frozen `ContainerProject`, that
      `reference_project()` carries the committed file's own header text, and
      that a project rendered by `resolve_project(...)` carries a **different**
      header naming itself generated and by which version — i.e. the string
      "reference artifact" appears in the reference render and in no operational
      render.
- [ ] T011 [P] [US2] (spec US2-S1) With a two-entry registry and a relocated
      `ERGANE_STATE_HOME`, assert the operational project carries same-path
      binds for the state root (`resolve_state_home() / "ergane"` —
      `factory/registry.py:159`, spelled as at
      `tests/test_088_us3_container_drift.py:322`), the supervision home
      (`factory/supervision/units.py:245`), the config directory, and both
      repos; that the `environment:` list still carries the bare passthrough
      names the committed drift derivation requires
      (`tests/test_088_us3_container_drift.py:239`); and that resolved values
      appear in the generated `.env` instead (R5).
- [ ] T012 [P] [US2] (spec US2-S1) Trap 3: assert the generated `.env` pins
      `ERGANE_CONFIG_PATH`, `ERGANE_PERSONAS_PATH` and `HOME` to resolved
      absolute host paths, and that the config directory is mounted same-path —
      the three facts that stop `resolve_default_registry_path`
      (`factory/config.py:111`) from taking its `:134` branch and silently
      falling back to the packaged example registry inside the engine. Assert the
      negative with the detector the tree already ships — `is_example_alias`
      (`factory/config.py:76`) — not a hand-rolled path comparison.
- [ ] T013 [P] [US2] (spec US2-S1) R6: assert `.env` pins
      `ERGANE_TEMPORAL_DB_FILENAME` to `resolve_state_home() / "ergane" /
      "temporal" / "engine.db"` — **not** to `container_supervisor.py:43`'s
      `/var/lib/ergane/temporal.sqlite`, which nothing mounts and the
      `Dockerfile` never creates, and **not** to `InstallLayout.temporal_db_path`
      (`factory/supervision/units.py:240`), which is the native managed
      Temporal unit's own file (`:500`). Assert both negatives explicitly, and
      assert the pinned path is covered by the state-root mount — the
      supervision-home mount does not cover it.
- [ ] T014 [P] [US2] (spec US2-S1) Trap 4: a mount source that no declared root
      covers, and a non-same-path bind, are each refused at generation time
      naming the path. The declared roots are the project's own mount set —
      state root, supervision home, config directory, every repo — so assert
      that the R6 database path passes the guard through the state-root mount.
      Assert `<path>:<path>` for every bind and no named volume anywhere in the
      render.
- [ ] T015 [P] [US2] (spec US2-S1) R7/R10: the image reference is derived from
      `importlib.metadata.version("ergane-cli")` through **module-private**
      helpers (the precedent is `factory/cli/main.py:131`, which this story does
      not edit — spec 105 claims the public vocabulary in
      `factory/supervision/engine_identity.py`); `image_source="local"` adds a
      `build:` stanza naming the install root and `Dockerfile`,
      `image_source="registry"` emits `image:` only; a failed version derivation
      refuses rather than guessing a tag; and `image_source="local"` against an
      install root holding **no** `Dockerfile` refuses by name, saying this
      installation has no build context and naming spec 105 as the fix.
- [ ] T016 [P] [US2] (spec US2-S1) R10 packaging: assert the confinement
      artifacts resolve as package data through the one helper — shaped on
      `factory/config.py:60` `shipped_registry_text()`, `importlib.resources`
      first and the checkout walk second — and that the text it returns for each
      equals the committed `container/seccomp-ergane.json` and
      `container/ergane-engine.profile`. Assert the wheel mapping exists in
      `pyproject.toml` by reading the `force-include` table, so a dropped entry
      fails here rather than at an operator's first wheel install.
- [ ] T017 [P] [US2] (spec US2-S3) Trap 9: assert the reference render carries
      no `unconfined` token, and that `reference_project()` fixes the
      confinement variant literally — no parameter reaches it — so the config-F
      branch is unreachable from that path rather than merely untaken.
- [ ] T018 [P] [US2] (spec US2-S2) Determinism: render the same project twice
      and assert the two texts are identical, and that the render is a function
      of the project data alone — no clock, no environment read at render time.
      (On-disk idempotence is US3's; this is the renderer's half of it.)

### Implementation for this story

- [ ] T019 [US2] (spec US2-S1, US2-S2, US2-S3) Write
      `factory/supervision/container_project.py` per R4: a frozen
      `ContainerProject` carrying data only (image reference, optional build
      stanza, confinement variant, mount tuple, env passthrough names, env
      assignments, published ports) plus the `header` and `annotations` comment
      fields, `reference_project()`, `resolve_project(...)` reading
      `factory/registry.py:159`, `factory/supervision/units.py:245`,
      `resolve_config_path()` and `load_registry()`, and
      `project_files(project) -> tuple[GeneratedFile, ...]` importing
      `GeneratedFile` from `factory/supervision/units.py:311`. Project
      directory: `supervision_home() / "container"`, holding `compose.yaml`,
      `.env`, and copies of the two confinement artifacts (so the relative
      `security_opt` paths resolve beside the compose file). This story renders
      those files; US3 writes them.
- [ ] T020 [US2] (spec US2-S1) R10: add the two `force-include` entries to
      `pyproject.toml:66`'s table mapping `container/seccomp-ergane.json` and
      `container/ergane-engine.profile` to `factory/container/<name>`, and write
      the one resolver that reads them — `importlib.resources.files("factory") /
      "container" / name` first, the `parents[1] / "container" / name` checkout
      walk second, exactly as `factory/config.py:60` does it. Every later reader
      of those artifacts (US4's consent prompt included) goes through this one
      function.
- [ ] T021 [US2] (spec US2-S1) Move the drift suite's env derivation
      (`tests/test_088_us3_container_drift.py:239`) into the new module as the
      one shared source, and have the test import it — this is the "shared
      constants" the spec's ruling names, and it is work rather than reuse
      because none exist today. All seventeen committed drift tests stay green.
- [ ] T022 [US2] (spec US2-S1) In `docs/container.md`, add to the
      Temporal-history section the container's own database path and why it is
      not the native tier's. **The existing text at `:29-31` is correct** — the
      native managed server does keep its database one directory above the
      supervision subdirectory, and the reference compose does mount both — so
      do not rewrite it; add the sentence that says the engine writes
      `engine.db` beside `dev.db` under the state root, that the state-root
      mount is what carries it across a recreate, and that a host migrating from
      the native tier starts with empty history unless the operator copies the
      file by hand.

### Verification for this story

- [ ] T023 [US2] (spec US2-S1, US2-S2, US2-S3) Commit
      `docs/104-us2-generated-project-transcript.md`, headed by one paragraph
      naming it a **seam capture** (rendered text only — nothing was written to
      a real supervision home, no daemon was contacted). It holds: the full
      rendered `compose.yaml` and `.env` for a two-repo registry, the structural
      + comment agreement result against `container/compose.reference.yaml`, the
      second render diff (empty), the local-build refusal on an install root
      with no `Dockerfile`, and the pasted `pytest` summary line for
      `tests/test_088_us3_container_drift.py` (seventeen tests, all passing).

## Phase 3: User Story 3 — The generated project is written, remembered and removable

### Tests for this story (write FIRST, must fail)

- [ ] T024 [US3] (spec US3-S1) In `tests/test_container_manifest.py`, with a
      tmp project directory: `write_project` writes every `GeneratedFile` from
      `project_files(...)` and records each file's digest in the manifest;
      a second `write_project` of the same project leaves both the directory
      contents and the manifest byte-identical. Red first: the module does not
      exist.
- [ ] T025 [P] [US3] (spec US3-S2) Hand-edit one written file, then write again:
      the writer refuses to overwrite it, naming the file — the
      `_is_someone_elses` rule (`factory/supervision/units.py:962`), not a
      filename allow-list, which is strictly weaker. Assert the refusal names
      the path and that the hand-edited content is still on disk afterwards.
- [ ] T026 [P] [US3] (spec US3-S2) `remove_project` removes only files whose
      recorded digest still matches, leaves the hand-edited file and any
      unclaimed file in the directory alone, and reports what it kept and why.
      `installed_project(layout)` returns the project record on a host that has
      one and `None` on a host that does not — that is the query R1 makes the
      installation's record, and US5, US6 and US7 all ask it.

### Implementation for this story

- [ ] T027 [US3] (spec US3-S1, US3-S2) Write
      `factory/supervision/container_manifest.py` per R11: `write_project`,
      `remove_project` and `installed_project` over the digest manifest,
      mirroring `factory/supervision/units.py:90` `MANIFEST_NAME`, `:962`
      `_is_someone_elses`, `:976` `_digest`, `:980` `_read_manifest` and `:990`
      `_write_manifest`. It imports `project_files` from
      `factory/supervision/container_project.py` and **edits that module not at
      all** — that is what keeps this story concurrent with US4.

### Verification for this story

- [ ] T028 [US3] (spec US3-S1, US3-S2) Commit
      `docs/104-us3-project-manifest-transcript.md`, headed by one paragraph
      naming it a **seam capture** (a tmp directory and the rendered project —
      no supervision home was touched). It holds: the written directory listing
      with the manifest's recorded digests, the second-write no-op, the refusal
      naming the hand-edited file, the removal listing what went and what stayed,
      and the pasted `pytest` summary line for
      `tests/test_container_manifest.py`.

## Phase 4: User Story 4 — The consent step loads the profile

### Tests for this story (write FIRST, must fail)

- [ ] T029 [US4] (spec US4-S1) In `tests/test_container_profile.py`, assert the
      transcript order through an injected prompter: the text of
      `container/ergane-engine.profile` — read through US2's package-data
      resolver (R10), so this works from a wheel — is printed **before** the
      prompt, the prompt's default is `y` (trap 7), and on consent the injected
      privileged runner is called once with an `apparmor_parser -r` argv naming
      the profile file. Then assert the project rendered from that decision
      names `apparmor=ergane-engine`.
- [ ] T030 [P] [US4] (spec US4-S2) Decline: the privileged runner is never
      called (assert on the seam's recorded calls, not on output), the config-F
      variant is rendered, and both the printed output and the generated file's
      **annotations** state the difference — including trap 8's measured fact
      that F depends on a host-loaded `/etc/apparmor.d/bwrap` stub that is not
      stock Ubuntu 24.04, and that G is the shipped configuration. The story
      promises a completely generated, honestly annotated engine whose remaining
      prerequisites are named — assert those words are in the file, not that the
      engine works.
- [ ] T031 [P] [US4] (spec US4-S3) `apparmor_parser` exits nonzero: its stderr
      is reported **verbatim**, the fallback to F carries the same statement as
      the decline path, and the project that results is a complete F project —
      never a half-configured one. Assert no partially written project directory
      survives the failure.

### Implementation for this story

- [ ] T032 [US4] (spec US4-S1, US4-S2, US4-S3) Write
      `factory/supervision/container_profile.py`: read the profile text through
      US2's package-data resolver, show it, prompt with `default="y"` and the
      trap-7 reasoning in the comment beside it, and run the load through an
      injected privileged runner (trap 11 — never a real `apparmor_parser` in a
      test). Return a `ProfileDecision` carrying the confinement variant,
      whether a privileged command was attempted, the verbatim failure text when
      there was one, and the operator-facing statement of the difference.
- [ ] T033 [US4] (spec US4-S2) In `factory/supervision/container_project.py`,
      add the confinement variant as a parameter of `resolve_project` **only**,
      keeping `reference_project()`'s value literal (trap 9), and carry the F
      variant's explanation as `annotations` on the project (R4) so it reaches
      the generated file as data — never as a string literal in the renderer,
      which would put it in every render. This is the one edit US4 makes to
      US2's module and the reason for the `concurrent_with` waiver against US3.

### Verification for this story

- [ ] T034 [US4] (spec US4-S1, US4-S2, US4-S3) Commit
      `docs/104-us4-consent-transcript.md`, headed by one paragraph naming it a
      **seam capture** and listing the seams (injected prompter, injected
      privileged runner — `apparmor_parser` was never executed and no kernel
      policy was touched). It holds all three captures: consent (profile text,
      prompt with its default, the *recorded* privileged argv, the resulting
      `security_opt`), decline (the seam's empty call list, the F compose
      fragment with its annotations), and parser failure (the stubbed stderr
      reproduced verbatim and the same fallback statement).

## Phase 5: User Story 5 — Bring-up, readiness and verify-through

### Tests for this story (write FIRST, must fail)

- [ ] T035 [US5] (spec US5-S1) In `tests/test_container_engine.py`, with the
      compose runner and the port probe both injected: bring-up calls
      `docker compose up -d` for the generated project, then waits **bounded**
      on the published Temporal address, and on timeout fails naming both the
      address and the timeout — the contract
      `factory/supervision/deploy.py:509` already states, with the same injected
      `now`/`sleep` seams.
- [ ] T036 [P] [US5] (spec US5-S1) Verify-through per R8: install runs
      `ergane install --verify` inside the engine through the runner seam,
      streams the child's stdout verbatim under a header naming the engine, and
      takes the child's exit code as the verdict. Assert **no parsing** of
      `[PASS] name: detail` back into `Finding` objects
      (`factory/controlplane/verify.py:1127`) — a version skew must surface as
      unreadable output, never as a silent pass.
- [ ] T037 [P] [US5] (spec US5-S2) A failing verify leaves the engine up: assert
      the runner recorded no `down`, no `stop` and no `rm`, and that the failure
      names a remedy.
- [ ] T038 [P] [US5] (spec US5-S3) Idempotent re-entry: against a half-up stack
      — project directory present, service reported up, port answering — a
      re-run regenerates (identical render, no-op write), re-ups, re-waits and
      re-verifies without error.
- [ ] T039 [P] [US5] (spec US5-S1) Trap 6: the published-port preflight. When
      the port answers and `docker compose ps` reports this project's service
      **not** running, refuse before `compose up`, naming the collision and both
      remedies (drain the native tier, or set `temporal.address` to a free
      port). When `ps` reports the service running, proceed — that is the same
      check that makes T038 converge.
- [ ] T040 [P] [US5] (spec US5-S4) R12, the address convention. Two assertions,
      both from the diff: (a) the generated `.env` sets
      `TEMPORAL_ADDRESS=127.0.0.1:7233` — the engine's own loopback in the
      tree-wide `host:port` spelling of `factory/notify/service.py:129` and
      `factory/cli/install.py:202`, never the host's published port; (b) driving
      `factory/supervision/container_supervisor.py`'s address resolution with
      that value yields `127.0.0.1:7233` and **not** `127.0.0.1:7233:7233`, and
      `_probe_temporal_address` (`:87`) splits it into host `127.0.0.1` and port
      `7233`. Cover the host-only spelling too, so the fix is compatible rather
      than a swap of one broken meaning for another.
- [ ] T041 [P] [US5] (spec US5-S1) End-to-end through `install_command` in
      **gateway** mode (trap 2 — direct mode raises `KeyError` inside
      `_interview_personas`), in `tests/test_install_container_bringup.py`:
      choosing `container` generates, consents, writes, brings up, waits and
      verifies in that order, and the personas registry is written before
      bring-up (R3).

### Implementation for this story

- [ ] T042 [US5] (spec US5-S1, US5-S3) Write
      `factory/supervision/container_engine.py`: the compose runner seam
      (`up`/`down`/`ps`/`exec`, fixed argv, no shell), the sync bounded
      readiness wait modelled on `factory/supervision/deploy.py:509` and
      `factory/supervision/container_supervisor.py:87`, the published-port
      preflight of T039, and the verify-through of R8.
- [ ] T043 [US5] (spec US5-S4) R12: in
      `factory/supervision/container_supervisor.py`, stop appending a port to an
      address that already carries one — `:220`'s
      `full_address = f"{temporal_address}:{temporal_port}"` — and make
      `_probe_temporal_address` (`:87`) split a single `host:port` value once.
      Keep `:39`'s constant honest about what it now means. Surgical: this is a
      defect fix inside 088's file, not a redesign of the supervisor, and
      `tests/test_container_supervisor.py` must stay green around it.
- [ ] T044 [US5] (spec US5-S1, US5-S2) In `factory/cli/install.py`, replace
      US1's placeholder print in `install_command` (`:687`) with the container
      branch: resolve the project, take US4's profile decision, write the
      project through US3's writer, preflight the port, bring up, wait, verify
      through the engine. Keep the native path's `verify_controlplane` call at
      `:722` for the `systemd` and `none` backends — the two other call sites
      (`:808`, `:902`) belong to `--non-interactive` and `--from-file`, which
      per US1-S3 resolve to `none` and must not change.
- [ ] T045 [US5] (spec US5-S2) Failure grammar: a verify that fails ends the
      install nonzero with the engine still up and a named remedy; a readiness
      timeout names address and timeout; neither tears anything down.

### Verification for this story

- [ ] T046 [US5] (spec US5-S1, US5-S2, US5-S3, US5-S4) Commit
      `docs/104-us5-bringup-transcript.md`, headed by one paragraph naming it a
      **seam capture** and listing the seams (injected compose runner, injected
      port probe, injected clock — no Docker daemon exists in this environment
      and none was contacted; the stubbed engine's verify output is the
      fixture's, not a real engine's, and is labelled as such where it appears).
      It holds: the bring-up capture ending in a passing verify-through, the
      failing-verify capture with the recorded runner calls showing no `down`,
      the re-entry capture against a half-up stack, the port-collision refusal,
      and the R12 address assertions with both spellings and their results. The
      real run against a real daemon is the first item of `plan.md`'s operator
      verification list.

## Phase 6: User Story 6 — `ergane init` reconciles the engine

### Tests for this story (write FIRST, must fail)

- [ ] T047 [US6] (spec US6-S1) In `tests/test_init_container_reconcile.py`,
      with the project writer and compose runner injected: `ergane init .`
      against a host whose generated project exists regenerates the mount list
      with the new repo at its own path, re-ups the engine, and prints one line
      about it in the report block at `factory/cli/init.py:809-823`. Against a
      host with no project — `installed_project(layout)` returning `None` —
      nothing is regenerated and nothing is printed.
- [ ] T048 [P] [US6] (spec US6-S1) `ergane init --check` reports the engine
      reconciliation as a finding through `gather_init_facts`
      (`factory/cli/init.py:1224`) / `run_check` (`:1344`), rather than as a new
      output surface.
- [ ] T049 [P] [US6] (spec US6-S2) In `tests/test_container_supervisor.py`,
      assert `_check_same_path_registry`'s refusal
      (`factory/supervision/container_supervisor.py:106`) names `ergane init`
      as the remedy for a repo whose recorded path is not mounted, while
      keeping the stale-cache remedy it already names. The existing test asserts
      only the word "remedies"; make the assertion specific.

### Implementation for this story

- [ ] T050 [US6] (spec US6-S1) In `factory/cli/init.py`, after `registration =
      _register(slug, repo_root)` (`:788`) and before `_schedule` (`:801`), call
      the regenerate-and-reconcile entry points that
      `factory/supervision/container_project.py`,
      `factory/supervision/container_manifest.py` and
      `factory/supervision/container_engine.py` already export — this story adds
      no function to any of them. Guard it on `installed_project(layout)` so a
      systemd-tier host is unaffected, and add the line to the printed report.
- [ ] T051 [US6] (spec US6-S2) Change the supervisor's same-path remedy at
      `factory/supervision/container_supervisor.py:130-133` to name
      `ergane init <repo path>`, and update the verbatim quote of it in
      `docs/container.md:22` in the same change — the doc and the string must
      not disagree.

### Verification for this story

- [ ] T052 [US6] (spec US6-S1, US6-S2) Commit
      `docs/104-us6-init-reconcile-transcript.md`, headed by one paragraph
      naming it a **seam capture** and listing the seams (injected writer and
      compose runner). It holds: the `ergane init .` capture showing the
      regenerated mount list and the reconcile line, the `--check` finding, the
      unchanged behaviour on a host with no project, and the supervisor's
      refusal text naming the new remedy beside the `docs/container.md` quote of
      it, so the pair can be read as identical in one place.

## Phase 7: User Story 7 — Uninstall unplugs cleanly

### Tests for this story (write FIRST, must fail)

- [ ] T053 [US7] (spec US7-S1) In `tests/test_teardown_container_step.py`, with
      `TeardownRequest.run` (`factory/cli/uninstall.py:106`) and the `steps`
      seam of `run_teardown` (`:803`) injected: the new step takes the engine
      down and removes only the files whose digests the project manifest
      recorded, while the state root and `config.toml` remain. Assert a
      hand-added file inside the project directory survives.
- [ ] T054 [P] [US7] (spec US7-S1) `--check` performs nothing: the survey names
      the engine and the project files, the runner records no call, and nothing
      is deleted — the survey/perform split
      `factory/cli/uninstall.py:130` and `:158` already enforce.
- [ ] T055 [P] [US7] (spec US7-S2) Purge extends to the generated artifacts with
      each removal named, and the step's `notes` state what it did **not**
      touch — the FR-013 symmetry `_survey_state` (`:493`) already uses. Assert
      `removal_targets` is wired so the FR-018 guard (`:725`) sees the project
      directory before any step acts.
- [ ] T056 [P] [US7] (spec US7-S1) Trap 13: with the Docker daemon unreachable
      (the injected runner raising), the step still surveys from the recorded
      manifest, reports that the engine could not be reached, and removes what
      it can — it does not raise. This is `_uninstall`'s deliberate omission of
      `factory/cli/nouns/worker.py:30`, copied.
- [ ] T057 [P] [US7] (spec US7-S1) Trap 12: update
      `tests/test_teardown_owns_the_ordering.py` and
      `tests/test_teardown_names_what_it_kept.py` for six steps and the new
      index grammar. Red first against the five-step assertions, so the diff
      shows the renumbering was deliberate.

### Implementation for this story

- [ ] T058 [US7] (spec US7-S1, US7-S2) Add the engine-container `Step` to
      `factory/cli/uninstall.py:702`'s `STEPS` at position **3**, immediately
      before `stop and remove units` (R9): dispatch is paused first,
      repositories are forgotten second, and the engine must be down before
      `clear state` could remove anything it is writing. Its `survey` reads the
      manifest and reports; its `perform` calls the `down` and `remove_project`
      entry points `factory/supervision/container_engine.py` and
      `factory/supervision/container_manifest.py` already export — this story
      adds no function to either module. Give it `removal_targets` so the
      self-deletion guard sees the project directory.

### Verification for this story

- [ ] T059 [US7] (spec US7-S1, US7-S2) Commit
      `docs/104-us7-teardown-transcript.md`, headed by one paragraph naming it a
      **seam capture** and listing the seams (injected `TeardownRequest.run` and
      `steps`). It holds: the six-step `--check` plan, the perform capture
      showing the recorded `down` call and the project removed with the state
      root and config named as kept, the `--purge` capture naming each removal,
      and the daemon-unreachable capture where the runner raised and the step
      reported rather than failed.
