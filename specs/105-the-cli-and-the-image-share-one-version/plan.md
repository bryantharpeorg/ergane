# Implementation Plan: the CLI and the image share one version

**Spec**: `specs/105-the-cli-and-the-image-share-one-version/spec.md`
**Evidence base**: `docs/container-onramp-research-findings.md` §4 (the version
contract) and §8 failure modes 6, 9 and 13. `docs/container-onramp-program.md`
decision 4 is the ruling; do not reopen it here.

**What landed first, and what that changes.** Spec 088 landed on 2026-08-24.
`Dockerfile`, `container/compose.reference.yaml`,
`factory/supervision/container_supervisor.py` and
`tests/test_088_us3_container_drift.py` are real files on the landing branch,
not aspirations. Two of them already commit to this spec's contract:
`container/compose.reference.yaml:10` is
`image: ghcr.io/bryantharpeorg/ergane:${ERGANE_VERSION}` and
`docs/container.md:69-75` already documents `FROM ghcr.io/bryantharpeorg/ergane:X.Y.Z`
and "the tag `X.Y.Z` is always equal to the CLI version". **105 is implementing
a contract that already landed, not authoring one.** Nothing in Python sets,
reads or defaults `ERGANE_VERSION` today, which is why `docker compose up`
against that reference file currently produces `image: ghcr.io/…/ergane:` and a
docker invalid-reference error. This spec is what produces that value.

## Requirements, numbered here

`spec.md`'s Requirements section is a one-paragraph summary that says
"numbered at refinement". These are those numbers. They live in this document
because `plan.md` is one of the three files assembled into every attempt
prompt (`factory/workgraph/prompt.py:65-68`,
`factory/workgraph/preflight.py:201`), so they reach the implementer intact.
The compiled Work Graph in `spec.md` carries `implements: []` on every node;
the mapping in this plan's Work Graph block is the plan's own and is what the
tasks cite.

**Three numbers are out of order on purpose.** FR-021, FR-022 and FR-023 were
added by the 2026-08-24 review repair and sit inside their own stories' blocks
(US2, US3, US4) rather than at the end, but they are numbered past FR-020 so
that no FR citation already written into `tasks.md` shifts. Read the blocks, not
the sequence.

**US1 — the release workflow gains the image job**

- **FR-001**: The image job MUST be a second job **inside**
  `.github/workflows/release.yml`, on the existing tag trigger (`:15-18`),
  declaring `needs: [build-and-publish]` — the id of the only job that exists
  (`:21`). No second workflow file.
- **FR-002**: Both platforms MUST be pushed by ONE
  `docker buildx build --platform linux/amd64,linux/arm64 --push` invocation.
  Never per-arch jobs pushing the same tag.
- **FR-003**: The image tag MUST derive from `GITHUB_REF_NAME` with the leading
  `v` stripped — the same value `:31-41` already proved equal to
  `pyproject.toml:3`'s `[project].version`. One source, two consumers.
- **FR-004**: GHCR login MUST use `GITHUB_TOKEN`, and `packages: write` MUST be
  declared on the **new job's own** `permissions:` block.
  `build-and-publish`'s block (`:24-26`) MUST remain exactly
  `contents: read` + `id-token: write`.
- **FR-005**: The job MUST sign the pushed digest with cosign keyless
  (`id-token: write`), and MUST fail the release when
  `docker buildx imagetools inspect` does not report both platforms.
- **FR-006**: A `.dockerignore` MUST exist. It MUST exclude `.git`, `.venv`,
  `.factory`, `.claude`, `dist`, `build`, `**/__pycache__` and `*.egg-info`,
  and MUST NOT exclude `pyproject.toml`, `README.md`, `personas.example.yaml`
  or `factory/` — the wheel's `readme` and its force-include
  (`pyproject.toml:5`, `:67-68`) need the last two.
- **FR-007**: A committed drift test MUST prove FR-001…FR-006 by parsing the
  committed files, **deriving** the image repository from
  `container/compose.reference.yaml:10` rather than restating it.

**US2 — the engine writes its identity**

- **FR-008**: One new module MUST own the engine-identity vocabulary:
  the filename constant, `identity_path(state_home)`, an `EngineIdentity`
  record, `write_identity`, `read_identity`, `cli_version()`,
  `IMAGE_REPOSITORY` and `image_reference(version)`. It MUST import nothing
  heavier than the standard library (no Temporal, no systemd, no registry) —
  the host CLI imports it on the `build start` path.
- **FR-009**: `cli_version()` MUST be the single answer to "what version is
  this CLI". `factory/cli/main.py:131-135` already resolves
  `importlib.metadata.version("ergane-cli")` with an `"unknown"` fallback; it
  MUST be rewired to call `cli_version()` rather than keep a second copy.
- **FR-010**: The supervisor MUST write the identity file **after** the
  readiness wait succeeds and **before** the worker child starts — between
  `factory/supervision/container_supervisor.py:256` and `:259` — deriving the
  path from the `state_home` local already resolved at `:211-214`.
- **FR-011**: The record MUST carry `version`, `started_at` (UTC, ISO-8601),
  `image_reference` (from `ERGANE_VERSION` when set, else `null`) and
  `image_digest` (from an injected `ERGANE_IMAGE_DIGEST` when set, else
  `null`). It MUST be written whole via temp-file-and-rename; a restart
  replaces it, never appends.
- **FR-021**: The identity record MUST have a **lifetime**. `_run_supervisor` MUST remove it in the `finally` block at
  `factory/supervision/container_supervisor.py:333-335`, so an engine that has
  stopped advertises nothing. The removal MUST be best-effort — missing file is
  not an error, and no failure there may change the function's return code or
  mask a child's exit status. The `try:` at `:298` is entered only after the
  identity write, so every path that wrote the record reaches that `finally`.
  See trap 24 for why this alone is not enough.

**US3 — the handshake refuses**

- **FR-012**: One pure comparison MUST produce the whole refusal sentence,
  naming **both versions**, the `docker pull` command for the pinned tag, and
  `ergane engine upgrade`. Absent identity file → no finding.
- **FR-022**: That same sentence MUST also name the **absolute path of the
  identity record**. FR-021 removes the record on a clean exit, but a SIGKILLed
  or `docker rm -f`'d container never runs that code, and the record outlives
  the container over the same-path bind mount
  (`container/compose.reference.yaml:21`, `:25`, with `HOME` passed through at
  `:34`). Without the path in the sentence, an operator whose engine is gone for
  good has no in-product way to clear a refusal that now blocks **both** dispatch
  sites permanently: `docker pull` is inert with no container running, and
  `ergane engine upgrade` refuses on a host with no project. The path is the
  escape hatch, and it must be in the sentence the operator is actually shown.
- **FR-013**: Both host CLI dispatch sites MUST refuse on mismatch:
  `factory/cli/nouns/build.py:316 _run_preflight` and
  `factory/workgraph/cli.py:119 _run_preflight`, emitting a
  `factory.workgraph.preflight.PreflightFinding` with `transport=False`. The
  host reads the record from `identity_path(resolve_state_home())` — the same
  absolute path the container wrote, because `compose.reference.yaml:34` passes
  `HOME` through and `:21`/`:25` mount the state root same-path. There is no
  second resolution rule and no container-only path to translate.
- **FR-014**: `ergane install --verify` MUST gain exactly one `Probe`
  (`factory/controlplane/verify.py:56`) registered in `REGISTRY` (`:1081`),
  returning a `factory.mergequeue.models.Finding`. On a host with no identity
  file it MUST return `passed=True` with an explanatory detail.
- **FR-015**: `ergane status` MUST surface the same fact by appending one
  string to `FloorStatus.notes` (`factory/cli/status.py:263`, appended at
  `:294`, returned at `:340`).
- **FR-016**: `docs/container.md:73-75` MUST be edited to state the remedy this
  spec actually prints.

**US4 — the upgrade verb drains first**

- **FR-017**: `ergane engine upgrade` MUST be one new noun file
  (`factory/cli/nouns/engine.py`) with every refusal and all orchestration in
  `factory/supervision/`, on the template of `factory/cli/nouns/worker.py`.
- **FR-023**: The compose project directory MUST be derived, not declared:
  `supervision_home() / "container"` (`factory/supervision/units.py:245`) — the
  exact path spec 104 has already committed to in writing
  (`specs/104…/plan.md`'s ruling **R1**). An `ERGANE_COMPOSE_PROJECT` environment
  variable MAY override it; nothing is required to set it. The verb MUST refuse
  when that directory or its `compose.yaml` is absent, naming the directory it
  looked in and `ergane install` as what creates it. It MUST NOT import
  `factory/supervision/container_project.py` — that module does not exist until
  104 lands — and MUST carry a comment naming 104's `installed_project(layout)`
  as the later delegation. Never guess a path, and never generate the project
  here.
- **FR-018**: It MUST refuse while any epic is open, naming them and what
  stopping now would cost, and proceed only under `--force`.
- **FR-019**: On a drained engine it MUST stop the engine, start the pinned
  new version, verify **through** it (the FR-014 probe answering green on the
  new version is the proof), and retain exactly the previous version's image
  while removing strictly older ones. **`degraded` is keyed on the engine
  finding alone.** `verify()` is `verify_controlplane`, which runs all seven
  probes in `REGISTRY` (`factory/controlplane/verify.py:1081-1089`) and collapses
  them to one exit code at `:1118` — so an unrelated red probe (the LLM proxy
  down, `gh` not capable) would otherwise fail an upgrade that succeeded. The
  report MUST carry every finding for the operator to read, and MUST set
  `degraded` only when the `check="engine"` finding is not passing.
- **FR-020**: Every docker interaction MUST go through one injectable seam. No
  test in this spec may run `docker`.

**Success criteria** (all pasted output, committed in the diff):

- **SC-001**: The US1 drift tests red-then-green — one paste per removed
  element.
- **SC-002**: A supervisor stub run's identity file, plus the same file after a
  restart, showing replacement not append, plus the directory listing after that
  supervisor exits, showing the record gone (FR-021).
- **SC-003**: The refusal at both dispatch sites, the probe's three verdicts
  (mismatch / match / absent), and the status note — every version string **and
  the identity record's path** visible (FR-022).
- **SC-004**: The upgrade verb refusing with epics in flight, refusing on a host
  where no project directory exists (FR-023), and the drained path's observed
  seam calls in order with the retention decision.

## What already exists, and where

**Every line number below was read individually off `346f811` on 2026-08-24.**
Re-check each before you edit it; a plan citing a moved anchor sends you
hunting at the operator's expense.

**US1 — the workflow you are extending (`.github/workflows/release.yml`):**

- `:15-18` — `on: push: tags: v[0-9]+.[0-9]+.[0-9]+`. The trigger is already
  right; do not add one.
- `:21` — `build-and-publish:`. **The only job in the file.** There is no job
  named `pypi`.
- `:23` — `timeout-minutes: 30`. Leave it. Your job declares its own.
- `:24-26` — `permissions: contents: read` + `id-token: write`. This block
  guards the PyPI trusted-publishing OIDC exchange. Your job gets its own
  block; this one is not edited.
- `:31-41` — "Validate tag against declared version": `GITHUB_REF_NAME` minus
  `v`, compared to `pyproject.toml [project].version`, `exit 1` before any
  upload. **FR-003's one source already exists here.**
- `:35` — `${{ matrix.python-version || '3.12' }}` inside a job that declares
  no matrix. It resolves to `'3.12'` today and is harmless. Do not add a
  `matrix:` to that job.
- `:68-74` — the publish step and its gate.

**US1 — the harness the drift test belongs in (`tests/test_release_path.py`):**

- `:25-26` — `WORKFLOWS_DIR`, `RELEASE_WORKFLOW`. Reuse them.
- `:272-316` — `_workflow_is_operator_tag_trigger_only`, a `yaml.safe_load`
  based `on:`-block analyzer.
- `:319` — `test_no_workflow_can_publish_on_branch_pr_or_merge_group`: every
  `.github/workflows/*.yml` containing the word "publish" must be operator-tag
  triggered. **Your edits are scanned by it, and so would a new workflow file
  be.** It must still pass.
- `tests/test_088_us3_container_drift.py:51 _repo_root`, `:76 _parse_dockerfile`,
  `:232 _load_compose` — the committed "parse the artifact, fail when a
  required element is removed" shape, landed yesterday. Your drift test is this
  shape, one file over.

**US1 — the build context you are fixing (`Dockerfile`, repo root):**

- `:44-49` — `COPY . /opt/ergane`, `WORKDIR`, `python3 -m venv .venv`,
  `pip install --no-cache-dir -e /opt/ergane`. **This is not a wheel install.**
- There is no `.dockerignore` (verified absent). `.git` is 39M and `.venv` is
  83M, and `.venv/pyvenv.cfg` points at an **aarch64 CPython 3.13** under
  `~/.local/share/uv/`. `:46` then runs `python3 -m venv .venv` over that
  copied directory **without `--clear`**, using Ubuntu 24.04's python3.12.
- `pyproject.toml:5 readme = "README.md"` and `:67-68`'s force-include of
  `personas.example.yaml` are why those two files must survive the ignore file.

**US2 — the insertion point (`factory/supervision/container_supervisor.py`):**

- `:197` — `async def _run_supervisor(config, *, start_child, probe_address)`,
  both seams injectable.
- `:211-214` — `state_home` resolved from `config["state_home"]`, then
  `ERGANE_STATE_HOME`, then `resolve_state_home()`; then
  `_check_same_path_registry(state_home)`.
- `:256` — `return 1`, the readiness-timeout exit. Nothing after this runs when
  Temporal never answered.
- `:259-260` — `worker` and `bridge` start. **FR-010's write goes between 256
  and 259.**
- `Dockerfile:59` — `ENTRYPOINT ["python3", "-m", "factory.supervision.container_supervisor"]`,
  pinned by `tests/test_088_us3_container_drift.py:106-112`. The identity write
  is inside this process; there is no other candidate.

**US2 — the state-home trap, in code (`factory/supervision/units.py`):**

- `:245 supervision_home()` = `resolve_state_home() / "ergane" / "supervision"`.
  It reads **env only**, via `factory/registry.py:159-171`. It cannot see the
  supervisor's `config["state_home"]`.
- `tests/test_container_supervisor.py:108-118` — the `config` fixture sets
  `state_home` to a tmp path but **does not relocate `HOME`**. Only
  `_relocated_state_home` (`:21-30`) does, and the startup-order tests never
  call it. Trap 3 below is this fact.

**US2 — the CLI half, already done (`factory/cli/main.py`):**

- `:131-135` — `_version_text()` resolving `importlib.metadata.version("ergane-cli")`
  with an `"unknown"` fallback. The spec never names it; it is the CLI side of
  the handshake and needs no new code, only relocating behind FR-009's
  function.
- `:53-96 _discover_nouns_with_failures` — noun discovery is
  `pkgutil.iter_modules` over `factory/cli/nouns/` with no literal name list,
  and no test pins the noun set. **US4 adds one file and touches no dispatcher.**

**US3 — the refusal channel that already exists:**

- `factory/cli/nouns/build.py:316 _run_preflight` → `:335 _preflight_exit_code`
  → the loop at `:684-695`, printing
  `ergane: preflight [<check>]: <detail>` on stderr and returning
  `EXIT_USER`/`EXIT_TRANSPORT`.
- `factory/workgraph/preflight.py:100 PreflightFinding` — frozen dataclass
  `(check, passed, detail, transport)`. The shared vocabulary. `transport=False`
  for a skew refusal: the operator's move is an upgrade, not "go look at the
  proxy".
- `factory/workgraph/cli.py:119 _run_preflight` / `:134 _preflight_exit_code` —
  a near-duplicate of the above, in a module still imported by
  `factory/cli/status.py:102`, `factory/cli/repo.py:59` and
  `factory/cli/doctor.py:51`, with its own `start_command` at `:496`.
  `tests/test_landing_dials_reach_the_epic.py:700-728` drives **both** sites.
- `factory/cli/nouns/build.py:571 start_command` — everything checkable without
  a server is checked before `_start_epic` opens a client. The skew read needs
  no server, but it must reach both sites, so it rides the preflight rather
  than sitting above `:613` in one of them.

**US3 — the probe (`factory/controlplane/verify.py`):**

- `:56 class Probe(Protocol)`, `:39 from factory.mergequeue.models import Finding`,
  `:1081 REGISTRY`.
- `:1024-1078 ForgeCapabilityProbe` — the exact precedent, including a docstring
  (`:1034-1041`) arguing why a first-run skew defect belongs in
  `install --verify` and not the doctor. That is the same argument this story
  makes; make it in your own docstring.
- `:1118` — `exit_code = 0 if all(f.passed for f in findings) else 1`. **There
  is no skip verdict.** See trap 4.

**US3 — the status surface (`factory/cli/status.py`):**

- `:263 FloorStatus.notes: list[str]`, appended in `collect_floor` from `:294`,
  returned at `:340`, rendered as `note: …` at `:728`, and carried into
  `--json` for free by `asdict(floor)` at `:274`. No new field, no new
  rendering.

**US3 — the native path you are NOT changing:**

- `factory/cli/nouns/build.py:741 _cli_revision` (git rev-parse behind the
  package seam `factory.cli.nouns._cli_revision_for_tests`, `__init__.py:37`)
  and `:761 _skew_notice`. `_skew_notice` compares **git revisions** carried in
  a *running epic's* query document (`:835-836`, sourced at
  `factory/worker.py:212`/`:318-319`, surfaced at
  `factory/workgraph/workflow.py:801`) and its only consumer is
  `_query_status` (`:836`) — i.e. `ergane build status`. Its tests are
  `tests/test_ergane_build_status_refusal.py`. See trap 1.

**US4 — the drain model spec 082 already built:**

- `factory/supervision/deploy.py:136 version_state`, `:151 DRAINED`,
  `:168-202 reapable` — **never the current version** (`:199`), only `DRAINED`
  (`:200`), and **unknown is not zero** (`:201`, docstring `:181-185`).
  `:224 SweepReport`, `:260 DeployReport`.
- `factory/versioning.py:137 OpenEpic`, `:150 predates_versioning`,
  `:163 strandable_epics`, `:171 open_epic_from` — the typed
  in-flight-work vocabulary.
- `factory/supervision/units.py:791-797` (uninstall) and `:894-905` (migrate) —
  two committed "refuse while work is in flight, name it, give the remedy"
  precedents with full wording, backed by `:996 _open_epics` and
  `:1029 _open_epic_ids`.
- `factory/cli/nouns/worker.py` (146 lines) — the thin-noun template; `:104-112`
  is the native tier's non-disruptive upgrade verb and states this spec's ethos
  in its own description.

## Technical approach, story by story

### US1 — the release workflow gains the image job

Two files change and one is created. `.dockerignore` is new; `release.yml`
gains a second job; the drift test goes beside `tests/test_release_path.py`'s
existing harness (in that file or a sibling importing its constants — either is
fine, a fresh bespoke YAML parser is not).

The image job: `runs-on: ubuntu-latest`, its own `timeout-minutes: 90`, its own
`permissions:` block with `contents: read` + `id-token: write` +
`packages: write`, `needs: [build-and-publish]`. Steps: checkout,
`docker/setup-qemu-action@v3`, `docker/setup-buildx-action@v3`,
`docker/login-action@v3` against `ghcr.io` with `${{ github.token }}`, one
`docker buildx build --platform linux/amd64,linux/arm64 --push
--tag <repo>:${TAG#v}` with `--iidfile`/`--metadata-file` so the digest is
readable, `sigstore/cosign-installer@v3` then `cosign sign --yes <repo>@<digest>`,
and finally `docker buildx imagetools inspect <repo>:${TAG#v}` piped through a
check that both `linux/amd64` and `linux/arm64` appear or the step exits 1.

The 90-minute timeout is a **declared decision, not the implementer's**: the
arm64 leg emulates an apt install, a NodeSource setup, an
`npm install -g @anthropic-ai/claude-code`, the uv installer and a venv+pip
install under QEMU on an amd64 runner. Thirty minutes reads as a flaky release
rather than a clean failure. Native arm64 runners are the future optimisation,
not this story.

`.dockerignore` is FR-006 and it is a **prerequisite of the first build, not a
tidiness item** — see traps 7 and 8.

The repository is declared **once** in the workflow, as a job-level `env:` key,
and the login, the build tag, the cosign target and the inspect assertion all
reference that one declaration. US1's test reads its value out of the workflow
and never restates it; tying that value to the rest of the tree is US3's job
(trap 14), which is what keeps US1 and US2 off each other's files.

The drift test asserts shape, never outcome: the job exists, its `needs` names
the real job, exactly one `buildx build` line carries both platforms, the login
uses the GitHub token, a cosign step signs a digest, the inspect assertion is
present, the tag expression reads `GITHUB_REF_NAME`, the ignore file's
include/exclude sets are as FR-006 states, and `build-and-publish`'s
`permissions` block is unchanged. Every one of those gets a red paste with the
element removed.

### US2 — the engine writes its identity

New module `factory/supervision/engine_identity.py` (FR-008). Standard library
only. Contents:

```
IDENTITY_FILENAME = "engine-identity.json"
IMAGE_REPOSITORY  = "ghcr.io/bryantharpeorg/ergane"
def cli_version() -> str                    # importlib.metadata, "unknown" fallback
def image_reference(version: str) -> str    # f"{IMAGE_REPOSITORY}:{version}"
def identity_path(state_home) -> Path       # state_home / "ergane" / "supervision" / IDENTITY_FILENAME
@dataclass(frozen=True) class EngineIdentity # version, started_at, image_reference, image_digest
def write_identity(state_home, identity)    # temp file + os.replace
def read_identity(state_home) -> EngineIdentity | None
```

`IMAGE_REPOSITORY` is pinned to `container/compose.reference.yaml:10` by a
test that parses that landed file and splits at `:${`. US1 does **not** read
that file — US3 is where the workflow's declaration, this constant and the
compose file are asserted equal (trap 14), which is what keeps US1 and US2
independent.

`identity_path` performs the same join `supervision_home()` performs, which is
why a test asserts
`identity_path(resolve_state_home()) == supervision_home() / IDENTITY_FILENAME`.
That pins them together **without** letting the supervisor call the env-only
resolver (trap 3).

The supervisor change is small and its placement is the whole story: after the
`probe_address` branch has been passed (i.e. after `:256` can no longer be
reached) and before `start_child("worker", …)` at `:259`. `state_home` is
already a local at that point.

The second half of that change is the **removal** (FR-021): one best-effort
unlink in the `finally` at `:333-335`, which today only removes the two signal
handlers. That `finally` belongs to the `try:` at `:298`, entered strictly after
the identity write, so every path that created the record runs it — clean
SIGTERM shutdown, a child dying first, or an exception out of the wait loop.
`missing_ok=True`, no exception escaping, and no touching of the return value
below it: the function's exit code is the fault report and the unlink is not
allowed to edit it.

FR-009's rewire: `factory/cli/main.py:131-135` loses its own
`importlib.metadata` call and gains `from factory.supervision.engine_identity
import cli_version`. `_version_text`'s output string does not change; the
existing `--version` tests must pass unmodified.

### US3 — the handshake refuses

One comparison, three surfaces, one sentence.

`engine_skew(identity, cli) -> str | None` is added to the US2 module and is
the only place the wording lives:

```
engine is running ergane <engine>; this CLI is <cli> — they must match.
Upgrade with `ergane engine upgrade`, or pull the pinned image directly:
docker pull ghcr.io/bryantharpeorg/ergane:<cli>
If that engine is gone, this record is stale — remove <identity path>.
```

That fourth line is FR-022 and it is not decoration. Both remedies above it
assume an engine that still exists: `docker pull` is inert when nothing is
running, and `ergane engine upgrade` refuses on a host with no generated project
(FR-023). The record, meanwhile, sits on the host side of a same-path bind mount
and survives the container — so on the one path where FR-021's removal did not
run (`docker rm -f`, SIGKILL, an OOM kill), this sentence is the operator's only
in-product escape from a refusal that blocks both dispatch sites. The path is
`identity_path(resolve_state_home())`, rendered absolute, not an abbreviation.

`None` when the versions match **and** when there is no identity file. The
absent case is US3-S3's "behaviour is today's: the check activates only on
evidence", and it is also what keeps every native install green (trap 4).

Surfaces:

1. **Dispatch** (FR-013). A new `engine_skew_findings(...)` in
   `factory/workgraph/preflight.py` returning `[PreflightFinding(check="engine",
   passed=False, detail=<the sentence>, transport=False)]` or `[]`, called from
   `factory/cli/nouns/build.py:316` and `factory/workgraph/cli.py:119`.
   Both. See trap 5.
2. **`install --verify`** (FR-014). One probe class beside
   `ForgeCapabilityProbe` (`factory/controlplane/verify.py:1024`), one
   `REGISTRY` entry at `:1081`. Its `gather` reads a file; its `evaluate`
   returns `Finding(check="engine", passed=…, detail=…)`.
3. **`ergane status`** (FR-015). One `notes.append(...)` in `collect_floor`
   near `:294` — in the **corpus half, above the `_open_client` call at
   `:299`**, so the note survives a Temporal outage rather than disappearing on
   the day the operator most needs it. No test drives `collect_floor` today
   (`tests/test_ergane_status.py` names it structurally at `:1518` and `:1855`
   and nothing else), so build the harness the cheap way rather than inventing
   one: `collect_floor` imports `_open_client` **inside the function** at `:299`,
   and that seam exists to be patched (`factory/cli/nouns/__init__.py:42`, "tests
   patch this seam"). Patch it to raise `OperatorError`, point `specs_root` at a
   `tmp_path`, and `asyncio.run(collect_floor(...))` returns a `FloorStatus`
   without a server anywhere. The assertion is on `notes`, and `degraded=True`
   from the absent client is expected and irrelevant.
4. **One repository string** (FR-012's remedy). One test asserting the
   workflow's single declaration, `container/compose.reference.yaml:10`'s
   image, and `IMAGE_REPOSITORY` are the same string. It lives here because
   the refusal sentence tells an operator which tag to pull, and that tag has
   to be the tag CI pushed.

`docs/container.md:73-75` is edited to name both remedies (FR-016). US3 owns
that file for this epic; US4 appends and does not touch what US3 wrote
(trap 15).

**The roadmap is deliberately not touched.** `factory/activities/roadmap_activities.py:390
preflight_spec` is a real second dispatch route, and a version refusal there
would be a no-op by construction: the roadmap runs *inside* the engine, so
"the CLI" and "the engine" are the same process and the same version. There is
no host CLI to be skewed from. This is stated so nobody adds it later thinking
it was forgotten, and so nobody removes the note thinking it was an oversight.

### US4 — the upgrade verb drains first

`factory/cli/nouns/engine.py` is a thin noun in the shape of
`factory/cli/nouns/worker.py`: parser, one verb (`upgrade`, with `--force`),
exit code from a report. All logic in
`factory/supervision/engine_upgrade.py`.

The drain decision is **spec 082's rule applied to images**, not a new one.
Open epics come from `factory/supervision/units.py:996 _open_epics` /
`factory/versioning.py:171 open_epic_from`; the refusal's shape is
`units.py:791-797`. Retention follows `deploy.py:168-202`: never the version
that is now current, never the one immediately previous, and **unknown is not
zero** — if the running version cannot be read from the identity file, nothing
is removed at all.

Docker is reached through exactly one seam — a protocol with `stop()`,
`start(image_reference)`, `verify()`, `list_images()` and `remove_image(ref)` —
injected by every test and defaulted to a `docker compose` runner in
production. `verify()` is `verify_controlplane` against the new engine, which
after US3 includes the identity probe; that probe answering green **on the new
version** is FR-019's "verified through it".

**The compose project directory is not this spec's to generate — but it is this
spec's to find, and 104 has already said where it is.** FR-023. Resolve it as
`supervision_home() / "container"` (`factory/supervision/units.py:245`), which is
`specs/104…/plan.md`'s ruling **R1**, verbatim: *"`project_dir(layout) =
supervision_home() / "container"` holding `compose.yaml` and a digest manifest
**is** the record. US5 and US6 ask `installed_project(layout)`; they never ask
the config."*
`ERGANE_COMPOSE_PROJECT` survives only as an operator override for a project kept
somewhere else; nothing is required to set it, and no refusal may depend on it.

Refuse when that directory or its `compose.yaml` is absent, naming **the
directory that was looked in** and `ergane install` as what creates it. That
refusal is true today — nothing generates the project yet — and the verb starts
working the moment 104 lands, with no cross-spec negotiation and no second
sentence to rewrite.

*Corrected at review repair 2026-08-24.* This paragraph previously made
`ERGANE_COMPOSE_PROJECT` the **only** resolution rule and told the implementer to
name `ergane install` as "expected to set it once 104 lands". 104 has declined to
do that in writing: R1 puts the record in a generated directory, and R2 says
"there is no saved declaration to honour on a re-run". The variable is
set by nothing, before or after 104 — so as written, `ergane engine upgrade`
would have refused in every reachable configuration forever, the whole drained
path would have tested unreachable code, and a committed regression test would
have defended a refusal sentence that misdescribes the world. Deriving the path
costs one line and removes all three problems.

Do not import `factory/supervision/container_project.py`: it does not exist until
104 lands, and importing it makes this story undispatchable. Leave a comment
naming `installed_project(layout)` as the delegation a later change makes, so the
duplication is declared rather than discovered.

US4 also exports `ERGANE_VERSION=<cli_version()>` when it starts the engine —
that variable is declared in `container/compose.reference.yaml:10` and `:49`
and produced by nothing today (trap 9).

## Traps

**1. `_skew_notice` cannot be extended, and the spec's framing says otherwise.**
`spec.md`'s frontmatter calls `factory/cli/nouns/build.py:761` "the skew
precedent to extend, not duplicate". It compares **git revisions** read off a
*running epic's* query document; it needs an epic to exist. This spec's
question — "what version is this engine" — is asked *before* any epic exists.
Do not refactor `_skew_notice`, do not call it, and do not change
`_cli_revision` (`:741`) or the package seam at
`factory/cli/nouns/__init__.py:37`. `tests/test_ergane_build_status_refusal.py`
(seven call sites of `_set_cli_revision`, helper at `:366-372`) must pass
**unmodified**. It covers `ergane build status`, which this spec does not
touch. `ergane build start` has no warning semantics to preserve.

One consequence of US1 lands on this quarantined surface, and it is **declared
scope, not a defect to file later**: FR-006's `.dockerignore` excludes `.git`,
which ships in the image today (`Dockerfile:44` copies the whole context). After
it, `factory/worker.py:212 _worker_revision()` returns `None` inside the
container — it is exception-safe, the `except Exception` is at `:225`, so nothing
crashes — `_WORKER_REVISION` (`:232`) is `None`, and `_skew_notice`'s first
branch (`build.py:763-767`) makes `ergane build status` print "worker revision is
unknown (CLI revision X); the worker predates this check or is not a git
checkout" against **every** container engine, permanently. That is accepted: the
git-revision comparison was never meaningful for an image built from a release
tag, and this spec's version handshake is its replacement. Do **not** "fix" it by
re-including `.git` in the build context, and do not edit `_skew_notice` to
special-case it.

**2. The identity write goes between line 256 and line 259.**
`factory/supervision/container_supervisor.py:256` is `return 1` when Temporal
never answered. Writing the identity beside `_check_same_path_registry` at
`:214` advertises identity for an engine that never came up, and US3's
handshake would then wave `build start` through against a dead engine — a
mysterious failure instead of a clean one.

**3. Derive the identity path from the `state_home` local, never from
`supervision_home()`.** `factory/supervision/units.py:245` resolves from env
only (`factory/registry.py:159-171`) and cannot see the supervisor's
`config["state_home"]`. `tests/test_container_supervisor.py`'s `config` fixture
(`:108-118`) injects a tmp `state_home` but does **not** relocate `HOME`; only
`_relocated_state_home` (`:21-30`) does, and the startup-order tests never call
it. An env-derived path writes into the operator's real
`~/.local/state/ergane/supervision` during `pytest`.

**This trap is about the supervisor, and only the supervisor.** The host side is
the opposite case: US3's read and US4's project resolution (FR-023) run in the
host CLI, where there is no injected `config` and `supervision_home()` /
`resolve_state_home()` **are** the right answers — their tests point
`ERGANE_STATE_HOME` at a `tmp_path` (`factory/registry.py:159-171` honours it) and
are isolated that way. Do not read this trap as "never call `supervision_home()`
in this spec".

**4. `verify_controlplane` has no skip verdict.**
`factory/controlplane/verify.py:1118` is
`exit_code = 0 if all(f.passed for f in findings) else 1`. A missing identity
file — every native install, and every pre-105 container — MUST return
`passed=True` with an explanatory detail. A probe that fails on absence turns
every native `ergane install --verify` red and takes the existing verify tests
with it.

**5. There are two `_run_preflight` sites and a test drives both.**
`factory/cli/nouns/build.py:316` and `factory/workgraph/cli.py:119`.
The second is still imported by `factory/cli/status.py:102`,
`factory/cli/repo.py:59` and `factory/cli/doctor.py:51`, and
`tests/test_landing_dials_reach_the_epic.py:620` and `:700-728` assert both
sites carry operator config. Changing one either fails that test or leaves a
live door onto the same workflow unguarded.

**6. `Finding` means three different things in this tree.** Name the type in
every criterion you write. `factory.mergequeue.models.Finding` is what
`verify.py` uses (imported at `:39`). `factory.doctor.models.Finding:30` is the
doctor's. `factory.workgraph.preflight.PreflightFinding:100` is the dispatch
one. `ergane findings report` is a fourth, unrelated thing. `CONTEXT.md` flags
exactly this overload class.

**7. The image is not built from a wheel, and the build context is poisoned.**
`Dockerfile:44` is `COPY . /opt/ergane` and `:47` is an **editable** install.
There is no `.dockerignore`. `.git` is 39M and `.venv` is 83M. `.dockerignore`
must exclude both and must keep `pyproject.toml`, `README.md`,
`personas.example.yaml` and `factory/` — the last two because
`pyproject.toml:5` and `:67-68` need them.

**8. `.venv` in the context is an active bug, not a size problem.**
`.venv/pyvenv.cfg` on this host points at an aarch64 CPython 3.13 under
`~/.local/share/uv/`. `Dockerfile:46` runs `python3 -m venv .venv` over that
copied directory **without `--clear`**, using Ubuntu 24.04's python3.12. It
presents as a confusing pip/interpreter error and differs between the amd64 and
arm64 legs. The fix is the ignore file. Do not "fix" it by adding `--clear` and
shipping the 83M copy anyway.

**9. `ERGANE_VERSION` is declared and produced by nothing.** It appears exactly
twice in the tree (`container/compose.reference.yaml:10` and `:49`). Unset, it
substitutes empty and yields `image: ghcr.io/bryantharpeorg/ergane:` — a docker
invalid-reference error, not an Ergane refusal. This spec is its producer:
`image_reference(cli_version())` is the value, US4 exports it at engine start,
and US2's record carries whatever the running engine was actually given. Do not
leave this to 104: `specs/104-install-brings-the-container-up-configured/spec.md`
assigns it here in its own ruling list — "105 owns pull-by-version — until it
lands, [104's] local-build bootstrap is the documented path" — and `…/104…/plan.md`'s
ruling **R7** keeps 104's own version derivation module-private for the same
reason. (Cited without a line number, and with 104's story number elided,
because 104 is a draft under active refinement: on 2026-08-24 that sentence both
moved and changed which of its stories it names.)

**10. Nobody has ever built this Dockerfile.** No `docker`, `buildx`, `cosign`
or `ghcr` token exists anywhere outside `container/compose.reference.yaml` and
the docs. 088's drift tests only parse the Dockerfile as text
(`tests/test_088_us3_container_drift.py:76-120`). US1 is the file's first
execution and it happens under multi-arch buildx in CI. **Your criteria are the
drift tests, red then green.** The 0.4.0 release cut is the operator's
verification step (`docs/container-onramp-program.md:131`), outside this story.
Do not fabricate a build log and do not add a gate that shells out to docker.

**11. The image job declares its own `timeout-minutes: 90`.** Do not raise
`build-and-publish`'s 30 (`release.yml:23`) and do not add a `matrix:` to it —
`:35` interpolates `${{ matrix.python-version || '3.12' }}` in a job that
declares none, and a matrix would make that expression start resolving to
something unintended.

**12. Do not weaken the PyPI gate's permissions block.** `release.yml:24-26` is
`contents: read` + `id-token: write` and it guards the trusted-publishing OIDC
exchange. `packages: write` goes on the **new** job's own block.
`tests/test_release_path.py:319` must still pass.

**13. Extend `release.yml`; do not add a second workflow file.**
`tests/test_release_path.py:319` yaml-parses every workflow containing the word
"publish" and requires an operator-tag-only `on:` block. A new file falls under
the same scan, and a second publishing entry point is a second thing to keep
tag-gated.

**14. Derive, never restate — and the repository is derived in one place, by
US3.** The version comes out of `GITHUB_REF_NAME`, which `release.yml:31-41`
already proved equal to `pyproject.toml:3`. The repository is declared **once**
inside the workflow (US1), pinned to `container/compose.reference.yaml:10` by
`IMAGE_REPOSITORY` (US2), and the three are asserted equal in **one test, in
US3** — the story whose refusal sentence tells an operator which tag to pull,
and therefore the story that must be right about it. A hand-copied `0.4.0` or
`ghcr.io/...` literal in a test passes forever after someone changes the real
thing.

**15. Two landed remedies for one refusal, and one file both stories want.**
`docs/container.md:73-75` (landed 2026-08-24) says the handshake "prints the
exact `docker pull` command to run"; `spec.md:112` says it names the upgrade
verb. **It prints both**, and US3 edits that paragraph to say so. US3 owns
`docs/container.md` for this epic. US4 **appends a new section at the end of
that file** and edits nothing above it.

**16. US3 names a verb US4 has not landed yet.** That is deliberate. US4 is
`depends_on_merged: [US3]`, so for one merge window inside this epic the
refusal names `ergane engine upgrade` before it exists — which is why the same
sentence also carries the `docker pull` command, which always works. Do not
"fix" this by dropping the verb from the wording, and do not spell it
differently in the two stories.

**17. "Image digest when knowable" is not knowable at build time.** The digest
is computed on push, and Docker exposes no in-container image digest. The
record carries `image_digest`, populated only from an injected
`ERGANE_IMAGE_DIGEST` when an outside party sets it, and `null` otherwise. Do
not invent one, do not derive one from a tag, and do not shell out to docker
from inside the container to look for one.

**18. One version answer, not two.** `factory/cli/main.py:131-135` already
resolves `importlib.metadata.version("ergane-cli")` with an `"unknown"`
fallback. FR-009 moves that resolution into `cli_version()` and rewires
`_version_text` to call it. Leaving two copies is how the banner and the
handshake start disagreeing.

**19. The drain rule is already written; do not write a second one.**
`factory/supervision/deploy.py:168-202` is it — never the current version, only
`DRAINED`, and unknown is not zero. `factory/versioning.py:137/:163` and
`factory/supervision/units.py:996` are the reads. US4 is a second front-end
onto that machinery. Operator memory, twice paid for: a worker restart
mid-attempt wedges the epic.

**20. Refuse-while-in-flight has committed wording, twice.**
`factory/supervision/units.py:791-797` and `:894-905`. Copy the *shape* — name
what is in flight, name what stopping now costs, name what to do instead — not
the words.

**21. No test runs `docker`.** Every docker interaction in US4 goes through one
injected seam. This host has been OOM-killed by test-spawned processes before;
a test that starts a container is worse.

**22. `ergane spec derive --delta` with no `-o` overwrites the tracked
`specs/<dir>/workgraph.json`.** If you re-derive anything while working, pass
`-o` and write somewhere else.

**23. The judge sees the diff and the criteria, nothing else** (Principle VIII
/ D-037). Every success criterion is pasted output committed in the diff. "Run
X and observe Y" is not a criterion.

**24. A refusal that reads a file nothing deletes is a wedge, and removal alone
does not fix it.** The identity record lives on the host side of a same-path
bind mount (`container/compose.reference.yaml:21`, `:25`, `HOME` at `:34`), so it
outlives the container that wrote it. Without FR-021 an operator who stops the
container for good — or moves back to the native tier — is refused at **both**
dispatch sites forever by a record describing an engine that no longer exists,
with no remedy in the sentence that works: `docker pull` needs a running engine
to matter and `ergane engine upgrade` refuses with no project on disk. FR-021's
unlink closes the clean path; `docker rm -f`, SIGKILL and an OOM kill all skip
it, which is why FR-022 also puts the record's absolute path in the sentence.
Both, or neither is enough. Do not substitute a staleness heuristic on
`started_at` for either: a long-running engine is not a stale one, and a clock
comparison would start refusing correct engines.

**25. US4 derives the project directory; it does not read an environment
variable to find it.** `supervision_home() / "container"` is 104's committed
record (`specs/104…/plan.md`'s ruling **R1**), and 104's ruling **R2** says there is no
saved declaration to honour. An earlier draft of this plan made
`ERGANE_COMPOSE_PROJECT` the only resolution rule; nothing sets that variable in
this tree or in 104's, so the verb would have refused in every reachable
configuration and its drained path would have been unreachable code with tests
in front of it. The variable is an override and nothing more.

## Work Graph

```yaml
US1:
  id: us1
  story_key: US1
  persona: implementer
  depends_on: []
  depends_on_merged: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
US2:
  id: us2
  story_key: US2
  persona: implementer
  depends_on: []
  depends_on_merged: []
  implements: [FR-008, FR-009, FR-010, FR-011, FR-021]
US3:
  id: us3
  story_key: US3
  persona: implementer
  depends_on: []
  depends_on_merged: [US2]      # + US1, inferred from the shared workflow file
  implements: [FR-012, FR-013, FR-014, FR-015, FR-016, FR-022]
US4:
  id: us4
  story_key: US4
  persona: implementer
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-017, FR-018, FR-019, FR-020, FR-023]
```

This mirrors `spec.md`'s Work Graph exactly in edges and adds the FR mapping,
which `spec.md` leaves as `implements: []`. **The compiled graph comes from
`spec.md`**; the block above is the plan's reading of it. Verified by deriving
to a scratch path on 2026-08-24 (`--delta` with no `-o` overwrites the tracked
`workgraph.json`, trap 22): `us1 []`, `us2 []`, `us3 [us2, us1]`,
`us4 [us3]` — **chain depth 3, two nodes at the head.**

**Width, and why it stops where it does.** US1 and US2 dispatch immediately and
concurrently: their task slices name disjoint files. Every remaining edge is
real:

- **US3 needs US2 merged** — there is no identity file to compare against
  until US2 writes one, and US3 extends US2's module with the comparison.
- **US3 also waits on US1**, inferred rather than declared: US3's slice reads
  `.github/workflows/release.yml` for the one-repository-string assertion
  (trap 14) and US1 writes that file. The derivation names this edge on every
  `spec derive`; it is correct, and the advisory is not something to silence
  with `concurrent_with` — US3's test genuinely needs US1's version of the
  file.
- **US4 needs US3 merged** — FR-019's "verify through it" *is* US3's probe
  answering green on the new version, and both stories write
  `docs/container.md`. Serialising them buys a real code dependency and
  removes a doc conflict at the same time.

The one edge that was removed as false: US1 and US2 originally both read
`container/compose.reference.yaml`, which inferred `us2 ← us1` and pushed the
chain to depth 4 over a file **neither story writes**. The repository
assertion moved to US3 instead. Do not move it back.

## Sizing

**US1 is the one that will cost a second attempt if dispatched loosely.** It is
the first execution of a file nobody has ever built, its proof is drift tests
rather than a green release, and three of its traps (7, 8, 10) are about the
gap between "the workflow file looks right" and "the build works". The workflow
YAML itself is thirty lines; the judgement is in `.dockerignore` and in
refusing to claim more than the diff proves.

US2 is small and well-seamed: one standard-library module, one four-line
insertion at a named place, one best-effort unlink in an existing `finally`
(FR-021), tests that drop into an existing stub-child harness.

**US3 is the widest slice in the trio and it was weighed for a split.** Seven
files, four surfaces — the two `_run_preflight` sites, a `Probe` plus its
`REGISTRY` entry, the `FloorStatus` note, and `docs/container.md` — behind one
function. It stays whole because the surfaces are one or two lines each and they
share a single sentence that must not drift between them; splitting on the
seam ("the comparison plus the two dispatch sites" / "the probe, the status note
and the doc") buys a fourth rung and puts the wording in two attempts. The one
piece of that story that was genuinely unbuilt — a harness for `collect_floor`,
which no test drives today — is now named in the US3 approach above: patch
`_open_client` and call it directly. If an operator disagrees and splits it, the
seam is that sentence, and FR-012's function must land in the first half.

US4 is the largest body of new code but the least novel: the drain decision
already exists in `deploy.py` and is being re-fronted, and every docker
interaction is a stub in every test.

## What else is in flight, and why it does not collide

Specs 104 and 106 are at draft and neither is dispatched. 104 generates the
compose project US4 consumes, and the seam between them is a **path, not a
variable**: 104 puts the project at `supervision_home() / "container"`
(`specs/104…/plan.md`'s ruling **R1**) and US4 looks there (FR-023), refusing cleanly
while it is absent. Neither spec has to tell the other anything at runtime, so
the two can land in either order — 104 first makes the verb work, 105 first
leaves a refusal that is true.
106 touches `spec new` and `build ship` and shares no file. 087 and 099 are at
draft and name none of these files; 099 is worth reading anyway, because in a
container the recreate *is* the deploy, so its restart safety sits directly
under US4's path.

**104 has already ceded this spec's vocabulary, in writing.**
`specs/104…/plan.md`'s ruling **R7** tells 104's implementer to keep its version
derivation module-private inside `factory/supervision/container_project.py`, to
create no second public version module, and — in the sentence FR-009 depends on —
"do not edit `factory/cli/main.py`". Its "What else is in flight" section names
`factory/supervision/engine_identity.py`, `cli_version()`, `IMAGE_REPOSITORY` and
`image_reference(version)` as 105's. So FR-008 and FR-009 are uncontested.

*Every citation into 104 in this plan names a **ruling id or a section**, never a
line number, and that is deliberate.* The first draft carried three line anchors
into 104's plan and all three were off by a section (`:268-285` landed in R6,
about `ERGANE_TEMPORAL_DB_FILENAME`; `:537-541` and `:541-545` both landed in
104's sizing paragraph). Worse, 104 is a **draft under active refinement** — it
moved by more than a hundred lines on 2026-08-24 while this repair was being
written — so any line number quoted here is stale before it is read. Ruling ids
survive the edits; check the claim by its `**R<n>**` heading and its quoted text.

**Two real file overlaps survive, and both are across epics rather than inside
this one.**

1. `factory/supervision/container_supervisor.py`. 104's US5 edits `:130-133` —
   the remedy string inside the mount-registry `SupervisorRefusal` — while this
   spec's US2 inserts the identity write between `:256` and `:259` and the
   removal in the `finally` at `:333-335`.
2. `docs/container.md`. **This is the overlap the first draft missed** — it
   claimed one file overlap and there are two. 104 writes this file twice
   (`…/104…/tasks.md`'s T020, correcting the Temporal-history paragraph; and its
   T042, editing the quoted remedy at `docs/container.md:22`), and this spec
   writes it twice (T031 at `:73-75`, T041 appending a trailing section).

Every one of those is a different region, so the merges themselves are fine, and
104's own plan, in the same section, draws the operator conclusion anyway:
the two epics **should not be dispatched into the same attempt window against
those files**, because the loser of a speculative merge is ejected from the merge
group and that ejection is invisible to the landing poller. This is an operator
sequencing constraint, not an implementer one — there is nothing for the US2
implementer to do about it except stay inside the regions traps 2 and 24 already
name.

Inside this epic the file assignments are exclusive by design, with one
deliberate exception: `.github/workflows/release.yml` is **written** by US1 and
**read** by US3's one-repository-string test, which is why the derivation
infers `us3 ← us1`. `.dockerignore` is US1's alone;
`factory/supervision/engine_identity.py` is created by US2 and extended by US3;
`docs/container.md:73-75` is US3's and the new trailing section is US4's;
`factory/cli/nouns/engine.py` and `factory/supervision/engine_upgrade.py` are
US4's alone. Nothing in this spec edits `Dockerfile` except US1, and US1 edits
it only if it adds a version `LABEL` — which is optional and, if added, is
US1's exclusively.

## Dispatch hazards, for the operator running this epic

Not implementer scope; these are how the epic itself dies.

- **`--max-concurrent-nodes` stays at 1.** Above 1, nodes die with "Session ID
  already in use", surfaced misleadingly as `DETECT_FAILED` about a missing
  `stdout.log`. The tell is a 74-byte `stdout.log`
  (`workgraph/concurrent-nodes-collide-on-agent-session-ids`).
- **Clear stale node worktrees before dispatch.** A worktree left by a dispatch
  under a different `target_repo` is silently reused and surfaces only as a
  bare git refspec error *after* gates and judge have passed
  (`workgraph/a-stale-node-worktree-from-another-target-repo-is-silently-reused`).
- **Check what the target repo has checked out.** `open_landing_pr` takes the
  PR base from the target repo's currently checked-out branch
  (`merge/landing-base-comes-from-the-target-repos-checked-out-branch`).
- **Never hand-title a landing PR.** `factory/workgraph/landed.py:39` anchors
  the grammar on `<epic_id>/<node_id>: US<N> (#<pr>)`; a prose title makes the
  landing invisible to `ergane spec landed` and to `--delta` forever.
- **Do not run this epic and 104 concurrently.** Two files are written by both:
  `factory/supervision/container_supervisor.py` (104-US5 at `:130-133`; this
  spec's US2 between `:256` and `:259` and in the `finally` at `:333-335`) and
  `docs/container.md` (104's T020 and T042; this spec's T031 and T041). No pair
  of regions overlaps, so the merges themselves are fine — but a merge-group
  ejection is invisible to the poller, so the cost of losing the race is a rung
  you have to diagnose by hand with a scratch-worktree speculative merge. Land
  one epic, then dispatch the other.

## Verification the operator will run, independent of the gate

- **Cut 0.4.0.** The tag is the only proof the workflow runs. Watch the wheel
  publish, then the image job; confirm
  `docker buildx imagetools inspect ghcr.io/bryantharpeorg/ergane:0.4.0` reports
  both `linux/amd64` and `linux/arm64` in one manifest list, and
  `cosign verify` accepts the digest.
- **Time the arm64 leg.** If it lands near 90 minutes, native arm64 runners
  become the next decision rather than a bigger number.
- **Break the version on purpose.** Run the engine at one version, the CLI at
  another, and confirm `build start` refuses, `install --verify` fails on the
  engine probe alone, and `ergane status` prints the note — three surfaces, one
  sentence.
- **Confirm a native install is untouched.** `ergane install --verify` on this
  host, with no identity file anywhere, must be exactly as green as it is
  today.
- **Upgrade with an epic open, then upgrade drained.** The first must refuse by
  name; the second must leave exactly two ergane images on the host. This is the
  real-daemon half of US4 and it is **the operator's, not the implementer's**:
  no attempt has a docker socket, so every criterion in front of the judge is a
  seam capture through the injected runner (FR-020, trap 21). Until 104 lands
  there is no generated project on this host, so the reachable behaviour is
  FR-023's refusal — run the drained path once 104's `ergane install` has written
  `~/.local/state/ergane/supervision/container/compose.yaml`.
- **Stop the engine and confirm the record is gone.** `docker compose down`, then
  `ls ~/.local/state/ergane/supervision/engine-identity.json` — absent (FR-021).
  Then the nasty one: `docker rm -f` the container so the removal is skipped,
  confirm `ergane build start` refuses, and confirm the sentence it prints names
  the path well enough that deleting that file clears the refusal (FR-022). This
  is the wedge the review caught, and the only way to know it is closed is to
  cause it.
