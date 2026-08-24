# Implementation Plan: install brings the container up configured

**Spec**: `specs/104-install-brings-the-container-up-configured/spec.md`
**Evidence base**: `docs/container-onramp-research-findings.md` (§1 confinement,
§3 same-path state, §8 the fourteen named failure modes) and
`docs/container-onramp-program.md` decisions 1–4. Where a trap below says
"measured", the findings appendix is the experiment log. Do not re-derive a
decision this plan cites; they were bought with experiments.

**Depends on 088 merged.** Everything this spec generates, brings up and tears
down already exists on the landing branch: `Dockerfile`,
`container/compose.reference.yaml`, `container/seccomp-ergane.json`,
`container/ergane-engine.profile`, `factory/supervision/container_supervisor.py`,
`docs/container.md`, `tests/test_088_us3_container_drift.py`.

## Terminology: say "the engine container"

The word *container* now means three unrelated things in this tree and
`CONTEXT.md` disambiguates none of them: the Docker engine container (this
spec), bwrap's sandbox — `factory/workgraph/adapter.py`'s `container_path`
derives the **sandbox's** PATH and has nothing to do with Docker — and "a
container of specs" (`CONTEXT.md:239`, about epics). Spell the Docker one **the
engine container** in every symbol, message and comment you write, and never
name a new function `container_path`.

## What already exists, and where

**Every line number below was read individually off `346f811` on 2026-08-24.**
Check each one anyway before you edit it: 103's landing grew
`factory/cli/install.py` past 1650 lines and moved everything under it by ~440
lines, which is exactly how a plan that cites a stale anchor sends an agent
hunting at the operator's expense.

### US1 — the interview's existing shapes (`factory/cli/install.py`)

- `:1256` `_systemd_user_session_available()` — the capability predicate that
  decides whether a chosen mode is *possible on this host*. **The Docker
  predicate goes immediately beside it, in this same file**, not in a new
  module: `factory/cli/nouns/worker.py:19` already imports this one, and two
  capability probes in two places is how they stop agreeing.
- `:1277` `_ask_temporal` — the exact shape US1 copies: `_ask(...)` with an
  `apply=` function, then a guard at `:1288-1294` that raises `OperatorError`
  when the chosen mode is unsupportable on this host. US1-S2's "refuses naming
  the daemon as missing" is that guard with a Docker predicate.
- `:1391` `_ask` — the question primitive (`default=`, `apply=`,
  `unavailable_error=`). Use it; do not invent a second prompt shape.
- `:1578-1582` `_OfferedLLM`, `:1585` `_llm_scan`, `:1602` `_offered_llm_mode`
  — a finished implementation of *probe, offer the probed answer first, keep a
  reason when the capable option is unavailable*. US1's `_offered_engine_backend`
  is this function with `shutil.which("docker")` + a daemon ping in place of
  `scan_endpoints`. Note `_offered_llm_mode` also carries an "unavailable
  reason" the caller passes to `_ask` — that is where "Docker is not installed"
  belongs.
- `:1516` `_apply_llm_mode` and `:1561` `_apply_escalation_adapter` are the
  *seeding/clearing* apply functions; `:1555` `_apply_temporal_mode` is the
  degenerate one that just merges the answer. US1 needs no `apply` at all —
  see the carrier ruling below.
- `:516` `_interview_personas` — 103's landing and **the precedent US1 must
  follow**: a new install step that is *not* inside `_interview`. It is called
  from `install_command:717` alone, takes an injected prompter, and therefore
  adds zero positional answers to the answer-file path.
- `:687` `install_command`, `:709` `_interview(path)`, `:717` the
  `_interview_personas` call, `:722` `verify_controlplane`.
- `:761` `_install_non_interactive` (prompter at `:799`, verify at `:808`) and
  `:855` `_install_from_file` (prompter at `:893`, verify at `:902`) — the two
  paths US1-S3 must leave untouched.
- `:1125` `_interview` — the single interview shared by all three paths. **Do
  not add the engine question here.** `:946` `_plan_file_answers` builds a
  positional answer list consumed in order by `_FilePrompter.ask` (`:839`); a
  question added inside `_interview` without a matching `take()` at the same
  ordinal desynchronises every later answer and surfaces as "file-driven
  prompter ran out of answers at *the last prompt*", naming the wrong question.
- `:192` `BLANK_DOCUMENT` — `temporal.address` defaults to `127.0.0.1:7233`.
  Read that line before you read trap 6.
- `factory/cli/nouns/install.py:119` `add_parser` (`--verify` at `:130`) and
  `:153` `_run`, the dispatch ladder. US1's `--engine` flag goes here.

### US2 — the machinery the generator is built from

- `factory/supervision/units.py:311` `GeneratedFile(name, text, directory,
  mode)` and `:335` `generated_files(layout)` — "every file `install` writes,
  **rendered from `layout` and nothing else**". Import `GeneratedFile`; express
  the engine-container project as a tuple of these. US2-S2's render
  determinism is then structural rather than tested into existence, and US3's
  writer takes that tuple whole.
- `factory/supervision/units.py:182` `InstallLayout`, `:203` `roots` — "a
  generated unit that references a path outside these starts, restarts and
  supervises perfectly on the one host where that path happens to exist." The
  engine-container project needs the same guard, for the same reason (trap 4).
- `:245` `supervision_home()` = `resolve_state_home() / "ergane" /
  "supervision"`, `:255` `resolve_layout()` (whose `generated_dir` defaults to
  `supervision_home()` at `:281-283`), `:240` `InstallLayout.temporal_db_path`
  = `generated_dir.parent / "temporal" / "dev.db"` — i.e.
  `<state root>/temporal/dev.db`, which is **under the state root and not under
  the supervision home**. Read R6 with that sentence in front of you; the
  reference compose mounts the state root at
  `container/compose.reference.yaml:21` and that is the mount which covers it.
  `:500` `_temporal_text` hands that same file to the **native** managed
  Temporal unit, which is why R6 does not reuse it.
- `factory/config.py:60` `shipped_registry_text()` — the tree's one worked
  example of *read a repo-root file as package data in a wheel and from the
  checkout otherwise*: `importlib.resources.files("factory") / NAME` first, the
  `parents[1]` walk second. `pyproject.toml:48-49`
  (`packages = ["factory"]`) and `:66-67` (the `force-include` of
  `personas.example.yaml` → `factory/personas.yaml`) are the two halves that
  make it work. R10 copies both halves for the confinement artifacts.
- `factory/registry.py:159` `resolve_state_home()` — **returns
  `~/.local/state`, not `~/.local/state/ergane`.** `:183`
  `resolve_registry_path()` appends `DEFAULT_REGISTRY_REL` (`:68` =
  `ergane/repos.json`). The state root the reference compose mounts is
  `resolve_state_home() / "ergane"`, which is how
  `tests/test_088_us3_container_drift.py:322` spells it. Copy that spelling.
- `factory/config.py:111` `resolve_default_registry_path` — `ERGANE_PERSONAS_PATH`
  → XDG (`~/.config/ergane/personas.yaml`) → **and then, at `:134`, silently
  falls back to the packaged example registry** through
  `_resolve_default_registry_path` (`:81`). Its own docstring calls that last
  branch deliberate (FR-004), so it will not be removed — it must be *avoided*.
  The tree already ships the detector: `is_example_alias` (`:76`) over
  `EXAMPLE_ALIAS_PREFIXES = ("example/",)` (`:57`). Assert with those rather
  than inventing a second notion of "is this the shipped example". Trap 3.
- `container/compose.reference.yaml:9` `services.ergane` (its `image:` is `:10`)
  — verified contents: `init: true`, `user: "1000:1000"`, `cap_drop: [ALL]`,
  `no-new-privileges:true`, `seccomp:./seccomp-ergane.json`,
  `apparmor=ergane-engine`, a **19**-name `environment:` passthrough list, three
  same-path `volumes:` entries (state root, supervision home, the example repo),
  and `x-ergane-repos` at the top level. The service declares exactly seven keys:
  `cap_drop`, `environment`, `image`, `init`, `security_opt`, `user`, `volumes`.
  Verified **absent**: any `ports:` key, any `build:` key, any config-directory
  mount.
- `tests/test_088_us3_container_drift.py` — **seventeen** tests, which is what
  `pytest --collect-only` reports: nine artifact tests (five Dockerfile at
  `:83-115`, two seccomp at `:135`/`:172`, two AppArmor at `:209`/`:221`) and
  eight compose tests (`:280`–`:380`). They all read
  `container/compose.reference.yaml` as a literal file (`COMPOSE_FILE`, `:48`).
  `:239` `_compose_environment_variable_names` derives the required passthrough
  set from `BLANK_DOCUMENT` and `_controlplane_default`; `:320` derives the mount
  expectation from `resolve_state_home()` and `supervision_home()`; `:380` bans
  the token `unconfined` anywhere in that file. **All seventeen stay green** —
  quote the count from a real run, do not restate this number. Trap 5.

### US3 — the writer's precedent, which already exists

- `factory/supervision/units.py:90` `MANIFEST_NAME = "installed.json"`, `:962`
  `_is_someone_elses`, `:976` `_digest`, `:980` `_read_manifest`, `:990`
  `_write_manifest` — digest provenance: *a file the engine did not write is
  never overwritten*, and symmetrically *teardown removes only files whose
  digest it recorded*. This one rule gives US2's "generated, never hand-edited"
  its teeth and gives US7 "removes what install generated — and nothing else".
  Do not reimplement it as a filename allow-list; that rule is strictly weaker.
  US3 is these five functions applied to a directory of `GeneratedFile`s, in a
  module of its own (R11) — not a rewrite of them.

### US4 — consent and the privileged act

- `factory/cli/init.py:268` `_CONSENT = ("y", "yes")`, sitting under the comment
  at `:265-267` that cites 060/FR-007 — "an absent answer is not an answer and a
  blank one is no more of one" — and `:271` `_confirm_resolved_root`, whose
  prompt at `:314-316` passes `default="n"`. (The function is at `:271`; only the
  prompt call is at `:315`. Read the comment at `:265`, not the call site, for
  the reasoning US4 is inverting.) **This is the codebase's only consent grammar
  and US4 must invert its default.** Trap 7 carries the operator's approval for
  that; read it before you write the prompt.
- `container/ergane-engine.profile` — the text to display and load. The profile
  name is `ergane-engine`; the load is `apparmor_parser -r <file>` under
  `sudo`, and it is the only privileged act in this spec.
- `docs/container.md:47-49` and findings §8 failure mode 3 — config F
  (`apparmor=unconfined`) works on this host only because a `/etc/apparmor.d/bwrap`
  stub is **hand-installed and unowned by any package**. Trap 8.

### US5 — bring-up, waiting and verifying

- `factory/supervision/deploy.py:509` `_await_registration` — the **sync**
  bounded-poll precedent, with injected `now()`/`sleep()` clock seams, a
  deadline, and the deliberate contract of returning the last observation on
  the timeout path ("a floor with a version that will not start is when an
  operator most needs the rest of the list"). US5's readiness wait and its
  "engine left up on failure" behaviour are this function's contract exactly.
- `factory/supervision/container_supervisor.py:87` `_probe_temporal_address` —
  the TCP half, already parameterised by `(address, timeout_s)`. It is `async`
  and lives inside the engine; US5 wants the same shape, sync, on the host
  side. Between it and `_await_registration` US5 writes almost no new waiting
  logic.
- **The address defect US5 is the first code path to hit.**
  `factory/notify/service.py:129` `DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"`
  — `host:port`, and that is the convention everywhere else in this tree:
  `BLANK_DOCUMENT["temporal"]["address"] = "127.0.0.1:7233"`
  (`factory/cli/install.py:202`), `factory/cli/env.py:84`,
  `scripts/ergane-env.sh`. But `factory/supervision/container_supervisor.py:39`
  defines its own `DEFAULT_TEMPORAL_ADDRESS = "127.0.0.1"` — host only — and
  `:220` builds `full_address = f"{temporal_address}:{temporal_port}"` from
  whatever `TEMPORAL_ADDRESS` holds. The reference compose passes
  `TEMPORAL_ADDRESS` through as a bare name
  (`container/compose.reference.yaml:43`), and the supervisor's children
  (`factory.worker`, `factory.notify.service`) read that same variable and
  expect a port in it. Hand the supervisor the tree-wide value and it builds
  `localhost:7233:7233`; `_probe_temporal_address`'s `rpartition(":")` then
  dials host `localhost:7233`, readiness times out and the engine never comes
  up. Hand it a host-only value and the children lose their port. R12 rules on
  it; it is 088's defect, inherited, and US5 is where it first bites.
- `factory/controlplane/verify.py:1081` `REGISTRY` (a module-level list of
  `Probe` instances), `:1095` `verify_controlplane_async` (takes only a
  config path), `:1122` `verify_controlplane`, `:1127` `render_findings`
  (emits plain `[PASS] <name>: <detail>` with no machine-readable form),
  `:301` `_inspect_host`, `:286` `_run_bwrap_probe`. **There is no seam for
  running this battery anywhere but in-process.** R8 rules on what US5
  does about that.
- `factory/cli/nouns/install.py:25` `_verify_command` — the verb US5 invokes
  *inside* the engine.
- `factory/cli/main.py:131` `_version_text` — the one existing derivation of
  the CLI version, `importlib.metadata.version("ergane-cli")` (verified: it
  answers `0.3.0` in this venv). `pyproject.toml:3` is the source of truth and
  there is no `factory.__version__`.

### US6 — `ergane init` reconciles

- `factory/cli/init.py:788` `registration = _register(slug, repo_root)` —
  US6's insertion point, before `_schedule` (`:801`) and `_wire` (`:805`); the
  printed report is `:809-823` and the closing `run_check` call is `:835`.
- `factory/cli/init.py:1224` `gather_init_facts`, `:1285` `check_repo`, `:1344`
  `run_check` — where an "engine reconciled" finding belongs for `ergane init
  --check`.
- `factory/supervision/container_supervisor.py:106` `_check_same_path_registry`
  and its remedy at `:130-133`, which today names **`ergane repo rebuild <repo
  path> ...`**, not `ergane init`. `tests/test_container_supervisor.py:340`
  asserts only the word "remedies", so the string is cheap to change — but
  `docs/container.md:22` quotes it verbatim and must change with it.

### US7 — teardown

- `factory/cli/uninstall.py:702` `STEPS` — the five-entry ordered table
  (`Step` at `:158`, `StepSurvey` at `:130`). `:106` `TeardownRequest` carries
  `run` and `open_epics` seams; `run_teardown:803` takes a `steps` seam.
  A container step is therefore testable with no Docker present.
- `:92-96` the five step-name constants; `:280` `_registered_repositories`;
  `:493` `_survey_state` and `:557` `_state_removal_targets` — **`clear state`
  acts only under `--purge`**, so without purge nothing else would remove the
  generated project. `:725` `_this_installation` and the FR-018 guard consume
  `removal_targets` before any step acts.
- `factory/cli/nouns/worker.py:30` `_require_systemd_user_session`, and the
  fact that `_uninstall` (`:49`) deliberately **does not** call it. Removal
  must work everywhere. US7 copies that asymmetry.

## Rulings this plan makes, so no story has to

These are decisions, not suggestions. A story that re-opens one spends its
attempt on a design argument that was already had.

**R1 — The carrier is the generated project on disk. Nothing goes in
`config.toml`.** `factory/controlplane/config.py:312` declares
`_TOP_LEVEL_KEYS = {"version", "llm", "memory", "temporal", "telemetry",
"escalation"}` and `:315` refuses any other top-level key by name. An
`[engine]` block would mean a new parser branch, a new `ControlPlaneConfig`
field, a `controlplane_document` round-trip, a renderer change and every
config round-trip test — for a fact that is not about the control plane at
all. Instead: the engine backend is a property of the *installation*, and the
installation records it the way the systemd tier does — by what it generated.
`project_dir(layout) = supervision_home() / "container"` holding
`compose.yaml` and a digest manifest **is** the record. US5, US6 and US7 ask
`installed_project(layout)`; they never ask the config.

**R2 — US1 persists nothing and reads nothing off disk.** The engine question
is probe-defaulted only: container first when a Docker daemon answers, else
systemd when a systemd user session answers, else none. There is no saved
declaration to honour on a re-run because R1 puts the record in a module US1
does not own. `_interview_engine` returns a value; `install_command` holds it
as a local. This is what keeps US1 and US2 concurrent.

**R3 — Ask early, act late.** `_interview_engine` is called from
`install_command` **before** `_interview_personas` (`:717`); the *acting* half
(generate, consent, up, wait, verify) runs after the personas registry is
written, because the engine reads that registry. The reason for the early ask
is that an interview reads better when every question is asked before anything
is done, and that a question placed after the persona step would be asked only
on hosts that got through it.

**It is not a reachability argument, and an earlier draft's was wrong.**
`_interview_personas` raises `OperatorError` when the gateway is unreachable,
so an install that cannot reach its gateway never reaches the acting half
either — asking first does not give that operator a container, it gives them
one more question. That is stated plainly in the spec's Assumptions instead of
being papered over here: **the container onramp requires a reachable gateway.**
Do not write a fallback for it in this spec.

**R4 — The generator renders both the reference and the operational project
from one renderer; comments are data; the agreement test is structural, not
byte-for-byte.** New module `factory/supervision/container_project.py`:

- a frozen `ContainerProject` dataclass carrying *data only* — image reference,
  optional build stanza, confinement variant, mount tuple, env passthrough
  names, env assignments, published ports, repo mounts — **plus two comment
  fields**: `header`, the comment block above `services:`, and `annotations`,
  comment lines keyed by the element they precede (a mount entry, the
  `x-ergane-repos` block);
- `reference_project()` → the symbolic one whose paths are the literal
  `${HOME}/...` strings, whose repo list is the committed example entry, and
  whose `header`/`annotations` are the committed file's own comment text;
- `resolve_project(...)` → the operational one, built from the confirmed
  config, `resolve_state_home()`, `supervision_home()`,
  `resolve_config_path()` and `load_registry()`, carrying **its own** header
  ("generated by `ergane install` <version>, do not hand-edit") and its own
  annotations;
- `project_files(project) -> tuple[GeneratedFile, ...]`.

**Why comments are data and not renderer literals.** The committed reference
carries a seven-line header that says "This is a reference artifact: `ergane
install` (spec 104) generates the operational project…"
(`container/compose.reference.yaml:1-6`), six comment lines interleaved inside
`volumes:` (`:19-20`, `:22-24`, `:26-28`) and three above `x-ergane-repos`
(`:51-53`). A renderer that hard-codes those strings emits "this is a reference
artifact" into the operational `compose.yaml` — a generated file that lies
about itself. Trap 8 and US4 need the same machinery anyway: the config-F
variant's explanation has to reach the generated file, and it is variant-
dependent text.

**Why the test is structural.** `render(reference_project())` is compared to
`container/compose.reference.yaml` two ways, and byte equality is **not** one
of them:

1. `yaml.safe_load` of both sides compares equal — every service key, both
   security options, every mount string, all nineteen environment names, and
   `x-ergane-repos`;
2. the ordered tuple of comment lines (every line whose first non-space
   character is `#`, stripped) compares equal.

Byte equality was considered and refused: the committed file is hand-written
and mixes flow (`cap_drop: [ALL]`) with block style, quotes `user: "1000:1000"`
but not `init: true`, and carries `${ERGANE_REPO_EXAMPLE:-/path/to/repo}`
interpolation. Pinning those choices makes the renderer a museum of one file's
whitespace, and the first legitimate reformat of the reference reads as a
generator defect. Structure plus comments is the fact "one fact, two files, one
test" was actually after. **Do not rewrite
`container/compose.reference.yaml`** — this story changes no committed byte of
it.

**R5 — Resolved values go in a generated `.env`, never into `environment:`
assignments.** `tests/test_088_us3_container_drift.py:239` requires the
compose `environment:` list to contain *bare names* like `ERGANE_STATE_HOME`
and `ERGANE_CONFIG_PATH`; an `ERGANE_STATE_HOME=/home/...` entry would not
match and the committed test goes red. Compose reads `.env` from the project
directory automatically, so the project is: `compose.yaml`, `.env`,
`seccomp-ergane.json` and `ergane-engine.profile` — copies of the committed
artifacts read through R10's package-data resolver, so `security_opt`'s
relative paths resolve beside the compose file. All four are `GeneratedFile`s
produced by US2's `project_files`. The fifth file, `installed.json`, is not one
of them: it is the manifest US3's writer keeps *about* the other four, and it
records their digests.

**R6 — The generated `.env` pins `ERGANE_TEMPORAL_DB_FILENAME` to the engine's
own file under the state root — not to the native tier's.** As landed,
`container_supervisor.py:43` `DEFAULT_DB_FILENAME =
"/var/lib/ergane/temporal.sqlite"`, the `Dockerfile` neither creates nor chowns
`/var/lib/ergane`, `USER` is `1000:1000` and nothing mounts it — so the engine
container writes Temporal history to an unmounted, probably unwritable path,
which is findings failure mode 5 exactly. The parser accepts
`ERGANE_TEMPORAL_DB_FILENAME` (`container_supervisor.py:391`). Pin it to:

```
resolve_state_home() / "ergane" / "temporal" / "engine.db"
```

**Two corrections to an earlier draft of this ruling, both load-bearing:**

1. **The covering mount is the state root, not the supervision home.**
   `InstallLayout.temporal_db_path` (`units.py:240`) is `generated_dir.parent /
   "temporal" / "dev.db"`, and `generated_dir` defaults to `supervision_home()`
   (`:281-283`) — so the file sits at `<state root>/temporal/…`, a *sibling* of
   the supervision home, not a child of it. `supervision_home()` is not in its
   parents. The reference compose mounts the state root at
   `container/compose.reference.yaml:21`, and that is the mount which covers
   it. Trap 4 tells you to refuse any path no mount covers; compute that
   coverage against **the project's whole declared mount set**, or the guard
   refuses the generator's own `.env`.
2. **It is not the same file the native tier writes.**
   `factory/supervision/units.py:500` `_temporal_text` hands
   `layout.temporal_db_path` — `dev.db` — to the native managed Temporal unit.
   Two Temporal servers on one SQLite file is the same-host corruption hazard
   findings §3 exists to prevent, and trap 6's second remedy ("set
   `temporal.address` to a free port") deliberately leaves both tiers running.
   So the engine gets `engine.db` beside it, and the two tiers never share a
   writer. The consequence, which is intended: **a host switching from the
   native tier to the container starts with empty workflow history.** Migrating
   is a documented operator move (stop both, copy `dev.db` to `engine.db`), not
   a code path this spec builds.

**R7 — The image reference is derived, and until 105 lands the project also
carries a `build:` stanza.** `importlib.metadata.version("ergane-cli")` is the
one derivation (`factory/cli/main.py:131`). **Keep 104's use of it private.**
Spec 105 is being refined in parallel and claims the public vocabulary —
`factory/supervision/engine_identity.py` owning `cli_version()`,
`IMAGE_REPOSITORY` and `image_reference(version)`. So US2 writes
`_engine_image_version()` / `_engine_image_reference()` as module-private
helpers inside `factory/supervision/container_project.py`, with a comment
naming 105 as the story that replaces their bodies with a delegation. Do not
create a second public version module; do not edit `factory/cli/main.py`. The
reference compose
declares `image: ghcr.io/bryantharpeorg/ergane:${ERGANE_VERSION}` and **no
`build:` key**, and that image does not exist on GHCR yet — a faithfully
derived project would attempt a pull and fail. `resolve_project` therefore
takes `image_source`: `"registry"` (reference variant, image only) or
`"local"` (default until 105, adding `build: {context: <install root>,
dockerfile: Dockerfile}` and tagging `ergane-local:<version>`). Never guess a
version; refuse when the derivation fails — and per R10, refuse the `"local"`
source itself, by name, when the install root holds no `Dockerfile`, because a
wheel install has no build context at all.

**R8 — Verify-through streams, it does not parse.** `verify_controlplane_async`
iterates a module-level `REGISTRY` in-process and `render_findings` emits free
text with no machine-readable form. US5 runs `ergane install --verify` **inside
the engine** through the runner seam, streams the child's stdout verbatim under
a header naming the engine, and takes the child's exit code as the verdict. Do
not parse `[PASS] name: detail` back into `Finding` objects: that is a
string-parsing contract between two versions of the same program, and it is how
a version skew becomes a silent pass. Do not invent a JSON mode mid-story
either — if one is wanted, it is a separate spec.

**R9 — The six teardown steps, in order.** The engine-container step is
inserted as step **3**, immediately before `stop and remove units`: dispatch is
paused first, repositories are forgotten second, and the engine must be down
before `clear state` could remove anything it is writing. The printed plan says
"N steps" from `len(table)`, so this renumbers every later step — trap 12.

**R10 — The two confinement artifacts ship in the wheel; the build context
does not, and the local-build path refuses by name when it is absent.**
Nothing in `factory/` reads `container/` today (`grep -rn docker factory/
--include=*.py` returns zero, and `factory/controlplane/verify.py:351` only
*names* those paths inside a remedy string), so this spec is the first runtime
coupling and it needs a packaging story before an agent discovers it mid-attempt.
`pyproject.toml:48-49` ships `packages = ["factory"]` and exactly one
force-include. Therefore:

- **`container/seccomp-ergane.json` and `container/ergane-engine.profile`
  become package data.** Add two `force-include` entries under
  `[tool.hatch.build.targets.wheel.force-include]` (`pyproject.toml:66`)
  mapping each to `factory/container/<name>`, and read them through one helper
  shaped exactly on `factory/config.py:60` `shipped_registry_text()` —
  `importlib.resources.files("factory") / "container" / name` first, the
  `parents[1] / "container" / name` checkout walk second. US2 needs their text
  to place copies beside the generated compose (R5); US4 needs the profile text
  to show before the consent prompt. Both work from a wheel after this.
- **`Dockerfile` does not, and cannot usefully, become package data.**
  `Dockerfile:44` is `COPY . /opt/ergane` followed by an editable install: the
  build context *is* the repository. A wheel install has no repository, and
  `resolve_layout`'s own docstring (`factory/supervision/units.py:265-268`)
  says `install_root` is `site-packages` there. So `image_source="local"`
  **refuses at generation time**, by name, when `install_root / "Dockerfile"`
  is not a file: *"this installation has no build context (installed from a
  wheel); the container tier needs a source checkout until the published image
  lands — spec 105"*. Refusing at generation is deliberate: it is the first act
  after the answer and before anything privileged, so the operator loses a
  prompt and nothing else.
- **US1 does not duplicate that predicate.** The engine question stays a
  question about the *daemon*; a second copy of "can this installation build an
  image" in `factory/cli/install.py` is exactly how two capability probes stop
  agreeing (the same argument that keeps `_docker_daemon_available` beside
  `_systemd_user_session_available`).

The spec's Assumptions now say this out loud, so it is a stated constraint
rather than a discovery.

**R11 — The writer is its own module, and US3 is its own story.** Rendering and
persisting are two jobs with two failure modes, and the risky one (R4) is all
in the rendering. `factory/supervision/container_manifest.py` owns
`write_project`, `remove_project` and `installed_project` over the digest
manifest, importing `project_files` from `container_project.py` and **editing
that module not at all**. US6 consumes `write_project`; US7 consumes
`remove_project`; US5 consumes both. That split is also what lets US3 and US4
run concurrently: US4 adds one parameter to the renderer while US3 never opens
it.

**R12 — One Temporal address convention, `host:port`, on both sides — and US5
fixes the supervisor to honour it.** The generated `.env` writes
`TEMPORAL_ADDRESS=127.0.0.1:7233`: the tree-wide spelling
(`factory/notify/service.py:129`, `factory/cli/install.py:202`), and the
engine's *own loopback*, because the supervisor's children live inside the
container — never the host's published port, which is a host-side fact that
belongs only in `config.toml`. That value is unusable to
`container_supervisor.py` as landed (`:39` host-only default, `:220`
`f"{temporal_address}:{temporal_port}"`), so US5 changes the supervisor:
when the resolved address already carries a port, it is the address — do not
append `DEFAULT_TEMPORAL_PORT` to it — and `_probe_temporal_address` (`:87`)
splits that single value once. The alternative (write a host-only value) is
refused: `factory.worker` and `factory.notify.service` read the same variable
out of the same environment and need the port. Two consumers, one variable,
one meaning. Keep the change surgical — it is a defect fix inside 088's file,
not a redesign of the supervisor — and cover it with a test that asserts the
built address for both spellings.

## Traps

**1. Do not put the engine question inside `_interview`.** Follow
`_interview_personas` (`factory/cli/install.py:516`): a separate step called
from `install_command`, taking an injected prompter. Inside `_interview`
(`:1125`) the question shifts a 15-entry positional answer list
(`tests/test_ergane_install_walkthrough.py:402` `GATEWAY_ANSWERS`, `:421`
`_answers`) that reaches **five** test modules: the one that defines it, three
that import it (`tests/test_install_mode_routing.py`,
`tests/test_direct_mode_refused.py`, `tests/test_controlplane_direct_mode.py`)
and one that duplicates it wholesale
(`tests/test_us2_shipped_registry.py:100`). The module that indexes by literal
position is the **definer** — `tests/test_ergane_install_walkthrough.py:568`
and `:660` — so a shift is not merely a length change there; it silently moves
which answer a positional index picks up. Five modules, not four: say five
wherever you restate this. US1-S3's "their existing tests pass unmodified" is
true by construction only if you stay outside `_interview`.

**2. Drive install end-to-end tests through *gateway* mode, never direct.**
`_interview_personas` (`factory/cli/install.py:528`) reads
`document["llm"]["master_key_env"]` unconditionally, and `_DIRECT_SEED`
(`:215`) has no such key — direct mode raises `KeyError`. This is 103's defect,
inherited, not yours. Do not spend the attempt diagnosing it and do not fix it
here.

**3. The engine container must be handed its config and persona registry by
explicit path, or it will run on `example/` aliases and look healthy.**
`resolve_default_registry_path` (`factory/config.py:111`) falls back at `:134` to
the *packaged example registry* when the operator file is absent, silently — and
`is_example_alias` (`:76`) is the check that catches it having happened. The
reference compose mounts no config directory and passes the host's `HOME`
through (`container/compose.reference.yaml:34`) while the image pins
`HOME=/home/ergane` (`Dockerfile:57`) — so inside the engine `~/.config` is a
directory that does not exist. The generated project must (a) mount the config
directory same-path, (b) set `ERGANE_CONFIG_PATH` and `ERGANE_PERSONAS_PATH`
to resolved absolute paths in `.env`, and (c) set `HOME` to the host user's
home. This does not fail at bring-up. It fails at the first dispatch, hours
later, which is the worst possible place for "verify passed" to have been
wrong.

**4. Refuse, at generation time, any project path that no mount covers.** Copy
`InstallLayout.roots`' *argument* (`factory/supervision/units.py:203`) — not
its tuple. The roots are **the project's own declared mount set**: the state
root, the supervision home, the config directory and every repo mount. Raise if
any path the compose or the `.env` names falls outside all of them. Compute it
that way or the guard refuses the generator's own `.env`: R6's database path is
covered by the **state-root** mount (`container/compose.reference.yaml:21`) and
by nothing else — `supervision_home()` is not in its parents. This is the guard
that would have caught `/var/lib/ergane` (R6) before it shipped, and it is the
check findings §8 item 12 asks for. Same-path only: every bind is `<path>:<path>`, no named volumes,
no overlays, no single-file mounts (measured — the one real same-host SQLite
corruption in the wild was an overlay giving sandboxes divergent copy-on-write
views).

**5. Call the resolvers; never copy the reference's literals.** The reference
hard-codes `${HOME}/.local/state/ergane`, while `resolve_state_home()`
(`factory/registry.py:159`) honours `ERGANE_STATE_HOME`, then the legacy
`FACTORY_STATE_HOME`, then `XDG_STATE_HOME`, then `~` — and both override
variables are in the compose passthrough list. A host that sets either gets a
container that resolves one path and is mounted at another. Note also that
`resolve_state_home()` returns `~/.local/state`; the state root is
`resolve_state_home() / "ergane"`, spelled that way at
`tests/test_088_us3_container_drift.py:322`.

**6. Publishing Temporal collides with the operator's own running factory.**
Verified on the floor host today: `127.0.0.1:7233` is held by the native
managed Temporal, and `BLANK_DOCUMENT` (`factory/cli/install.py:192`) defaults
`temporal.address` to exactly that. The generated project must publish a port
(the reference declares none, so the host CLI can reach nothing), and the
moment it does, an operator verifying this work collides with themselves — or
worse, the CLI talks to the *native* Temporal while the engine talks to
nothing, and everything looks fine. So: publish `127.0.0.1:<port>:7233` where
`<port>` comes from the confirmed `temporal.address`, and **probe that port
before `compose up`**. If something answers and it is not this project's own
service (ask `docker compose ps` for the project first — that is also what
makes US5-S3's re-entry converge), refuse naming the collision and both
remedies: drain the native tier, or set `temporal.address` to a free port. The
second remedy is only safe because R6 gives the engine its own SQLite file:
before that ruling, "run both on different ports" put two Temporal servers on
one `dev.db`.

**7. The sudo prompt defaults to YES, and that inverts the only consent
precedent in this repository.** `factory/cli/init.py:268` defines `_CONSENT =
("y", "yes")` and `_confirm_resolved_root` (`:271`) prompts with `default="n"` at
`:314-316`, under the comment at `:265-267` carrying 060/FR-007's rule that a
blank answer is not consent. **The operator has explicitly approved
default-yes for the AppArmor load**, because declining does not avoid the
privileged act on a fresh host (trap 8) and a default-no here produces a
config-F engine nobody chose. Write `default="y"`, show the profile text
*before* the prompt, and put this trap's reasoning in the code comment so the
next reader does not "fix" it back. An implementer who greps for consent will
find exactly one answer and it is the opposite one.

**8. Declining the profile does not mean "no privileged command".** US4-S2's
"no privileged command was attempted" is true *of this installer* and must be
implemented literally — the decline path runs nothing under sudo. But do not
also *claim* that config F is privilege-free: measured (findings §8 item 3),
F works on this host only because `/etc/apparmor.d/bwrap` is hand-installed and
unowned by any package; on stock Ubuntu 24.04 the F recipe fails at `uid_map`
with no obvious cause. The generated F variant's file comments and the
declined-path output must both say so, and must say that G is the shipped
configuration. Related and worth one sentence in the output: removing the
profile activates the kernel's capability-stripping `unprivileged_userns`
transition on Ubuntu ≥23.10, so "just turn AppArmor off to debug it" makes
things worse, always (findings §8 item 4).

**9. The config-F branch must be structurally unreachable from the reference
render.** `tests/test_088_us3_container_drift.py:380` bans the token
`unconfined` anywhere in `container/compose.reference.yaml`. Because R4 renders
both variants through one function, a parameter that merely *defaults* to G
leaves that committed test one wrong default away from red on a file nobody
edited. `reference_project()` must construct the G confinement literally, with
no parameter reaching it, and a test must assert the reference render carries
no `unconfined` token.

**10. Bring-up runs bwrap as a child, never as PID 1, and never as root.**
Measured: as container PID 1 bwrap fails `setting up uid map: Permission
denied` (findings §8 item 2) and as uid 0 it takes a `clone(CLONE_NEWNS)` path
needing `CAP_SYS_ADMIN` with the same EPERM text (item 1). `init: true` and
`user: "1000:1000"` are already in the reference; the generator must keep both
and must never emit a healthcheck or preflight that `docker run`s bwrap as the
entrypoint. The engine runs as the host uid — that is program decision 2 and
it is what puts bwrap on its working code path.

**11. Do not start a real Docker daemon, a real container or a real
`apparmor_parser` in any test.** Every process this spec spawns goes through an
injected runner seam, the way `TeardownRequest.run`
(`factory/cli/uninstall.py:106`) and `deploy._await_registration`'s
`now`/`sleep` (`factory/supervision/deploy.py:509`) already do. This host was
OOM-killed once by test-spawned orphans, and `apparmor_parser` edits kernel
policy. If a live check is genuinely unavoidable, guard it at call time by a
real capability check — never by a marker.

**12. Adding a sixth teardown step renumbers the printed plan.** `run_teardown`
(`factory/cli/uninstall.py:803`) prints `<index>/<total> <name>` and `_stop`
(`:779`) renders "stopped at step N of M … not attempted: …". Both
`tests/test_teardown_owns_the_ordering.py` and
`tests/test_teardown_names_what_it_kept.py` assert that grammar. US7 will
therefore present as a broad, unrelated-looking test diff. That is expected —
say so in the commit message rather than trimming the change to hide it.

**13. Bring-down may not require what bring-up requires.**
`factory/cli/nouns/worker.py:30` refuses three verbs without a systemd user
session, and `_uninstall` (`:49`) deliberately does not call it. Copy the
asymmetry: US7's step must survey and act sensibly on a host where the Docker
daemon has gone away — the recorded manifest still says what to remove, and a
project whose engine cannot be reached is reported, not raised.

**14. The judge sees the diff and the criteria, nothing else** (Principle VIII
/ D-037), and this spec's environment cannot produce a real transcript. The
agent sandbox binds no Docker socket — the bind list is built at
`factory/workgraph/adapter.py:477-524` and `/var/run/docker.sock` is not in it
— trap 11 forbids a real daemon, container or `apparmor_parser`, and R10 says
the local build needs a checkout the wheel does not carry. So **every
transcript this spec commits is a seam capture**: the output of the code under
test driven through the injected prompter, runner, clock and port seams, in a
file whose first lines say so and name the seams. Never "run X and observe Y",
and never a plausible-looking real transcript — under a judge that sees only
the diff those are indistinguishable, which is exactly why the label is part of
the criterion. The real-hardware runs are the operator's, in this plan's last
section, and no gate waits on them.

## Work Graph

Mirrors `spec.md`'s `## Work Graph` section, which is the one the compiler
reads. If they ever disagree, `spec.md` wins and this block is the bug.

```yaml
US1:
  persona: opus-closer
  depends_on: []
  depends_on_merged: []
  implements: []
US2:
  persona: opus-closer
  depends_on: []
  depends_on_merged: []
  implements: []
US3:
  persona: opus-closer
  depends_on: []
  depends_on_merged: [US2]
  implements: []
US4:
  persona: opus-closer
  depends_on: []
  depends_on_merged: [US2]
  concurrent_with: [US3]
  implements: []
US5:
  persona: opus-closer
  depends_on: []
  depends_on_merged: [US1, US2, US3, US4]
  implements: []
US6:
  persona: opus-closer
  depends_on: []
  depends_on_merged: [US5]
  implements: []
US7:
  persona: opus-closer
  depends_on: []
  depends_on_merged: [US5]
  concurrent_with: [US6]
  implements: []
```

**Why this shape.** `depends_on_merged` models what a story needs to *exist*,
not what it might touch, and the chain governs wall-clock.

- **US1 and US2 are concurrent.** R1 and R2 are what make that true: US1 asks a
  question and holds the answer as a local, so it never names the generator's
  module; US2 renders text and never touches `factory/cli/install.py`. Their
  task slices are disjoint.
- **US3 and US4 both wait for US2 merged, and are concurrent with each other.**
  US3 is the writer (R11) in `factory/supervision/container_manifest.py`; US4
  asserts that *the generated compose* names `apparmor=ergane-engine` and adds
  the confinement variant as one parameter of US2's renderer. US3's slice names
  `container_project.py` because it imports `project_files` from it, so
  `_with_contention_edges` (`factory/workgraph/derive.py:187`) would otherwise
  serialize the pair on a module only US4 edits; `concurrent_with: [US3]` on
  US4 is the statement that the pair was considered. Their edited files are
  disjoint by construction.
- **US5 waits for all four merged**: it wires US1's chosen backend to US4's
  consent decision, US2's renderer and US3's writer inside one
  `install_command` branch, and it edits the file US1 edits.
- **US6 and US7 are the second concurrent pair**, and both *call* US3's writer
  without editing it — US6 to regenerate the mount list, US7 to remove what was
  generated. Same waiver, same reason. Their edited files are disjoint by
  construction: US6 owns `factory/cli/init.py`,
  `factory/supervision/container_supervisor.py` and `docs/container.md`; US7
  owns `factory/cli/uninstall.py`.

Longest path: US2 → US3 → US5 → US6/US7. Chain depth 4 — unchanged by the US2
split, because the writer sits on a rung the consent story already occupied.
Width 2 at the first level, 2 in the middle and 2 at the last.

## Sizing

**US2 is still the largest and the one to watch, and it is now the renderer
alone.** "The generator and the reference compose share their constants"
describes *work*, not reuse: there are no shared constants today,
`container/compose.reference.yaml` is hand-written literal YAML, and the
committed drift suite parses that literal file. US2 must build the renderer,
prove its reference render agrees with the committed file in structure and in
comments (R4), carry the packaging change R10 names, and keep seventeen
committed tests green — and `grep -rn docker factory/ --include=*.py` currently
returns zero hits (verified 2026-08-24), so none of the Docker vocabulary
exists yet either.

**The writer came out of it deliberately (R11).** An earlier draft shipped the
manifest layer inside US2 so that no later story would have to edit the module.
That reasoning was backwards: it put the epic's highest-risk piece (R4) and a
mechanical, well-precedented persistence layer in one attempt, where a failure
in either discards both. As US3 the writer is small, has a five-function
precedent to copy (`units.py:962-990`), and runs concurrent with consent.

**US5 is the second largest** and is mostly wiring plus two bounded waits it
can model on `_await_registration`, with R12's supervisor fix on top. Its risk
is not size; it is R8, R12 and trap 6, all of which are decided above.

US1 is small if trap 1 is obeyed and large if it is not. US4 is small — one
prompt, one injected privileged runner, one fallback branch, one renderer
parameter — and its whole survival kit is traps 7, 8 and 9. US6 is small. US7
is small code with a broad test diff (trap 12).

## What else is in flight, and why it does not collide

Specs 087 and 099 are at draft; neither names `factory/cli/install.py`,
`factory/cli/init.py`, `factory/cli/uninstall.py`, `container/` or a new module
under `factory/supervision/`. 106's `spec new` / `build ship` stories are
independent.

**105 is the one to sequence against.** It creates
`factory/supervision/engine_identity.py` as the single owner of
`cli_version()`, `IMAGE_REPOSITORY` and `image_reference(version)`, rewires
`factory/cli/main.py:131-135` onto it, and inserts an identity write into
`factory/supervision/container_supervisor.py` between `:256` and `:259`. R7
keeps 104 out of that vocabulary, and 104's own edits to that file are US5's
address fix (R12, at `:39`/`:87`/`:220`) and US6's remedy string
(`:130-133`) — all different regions — but the two epics should not dispatch
into the same attempt window against that file if the operator can avoid it: a
speculative-merge ejection here costs a rung the poller cannot see.

R10 also touches `pyproject.toml`, which 105 does not.

099 is worth reading for a non-collision reason: in a container the recreate
*is* the deploy, so its restart-safety is load-bearing on this path.

## Verification the operator will run, independent of the gate

**This list is where the real hardware lives.** Trap 14 sends every committed
transcript through the seams; nothing below is a gate, nothing below blocks a
landing, and no story's acceptance criteria may cite an item on it. Read it as
the operator's own list, because that is what it is.

- **A real interactive `ergane install` on a host with the native tier
  drained**, choosing the container, consenting to the profile, watching the
  bounded wait and the verify-through pass. This is the run that makes the
  story real — and it is also the run that proves trap 6 was handled, because
  the collision check must have fired before the drain. It is also the only
  place the seam captures' claims meet a real daemon.
- **Decline the profile once** and read the generated F variant's comments:
  they must state the difference and the stub dependency.
- **Break the verify deliberately once** (a bad `llm.base_url` will do) and
  confirm the engine is still up afterwards and the failure named a remedy.
- **Re-run install against the half-up stack** left by the previous item and
  confirm it converges rather than erroring.
- **Point `temporal.address` at the port the native tier holds** and confirm
  the preflight refuses before `compose up`, naming both remedies.
- **`compose down && compose up` and confirm workflow history survives** —
  R6's whole reason to exist, and findings failure mode 5. Confirm at the same
  time that the file it survives in is the engine's own `engine.db` and that
  the native tier's `dev.db` beside it was not touched.
- **`ergane init .` in a second repo** and confirm the mount appears and the
  engine picks it up without a hand edit.
- **`ergane uninstall`** and confirm the engine is down, the project directory
  is gone, and the state root and `config.toml` are still there.
- **One real story dispatched inside the engine container against a scratch
  repo, watched to a landing.** A green suite and a PASS verdict are evidence,
  not proof; this is the proof.

*Operator note, not an implementer trap:* `ergane spec derive --delta` with no
`-o` overwrites the tracked `specs/<dir>/workgraph.json`. It matters when you
reason about this epic's graph from an operator session; an implementer node
has no reason to run it and this plan does not ask one to.
