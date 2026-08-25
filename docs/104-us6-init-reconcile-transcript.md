# 104-US6 — `ergane init` reconciles the engine (seam capture)

**This is a seam capture, not a live run.** Every line below was produced by the
code under test driven through injected seams, in `tests/`, on a scratch host
under `tmp_path`. No Docker daemon was contacted, no container started, no
kernel policy touched (plan traps 11 and 14). The seams closed are:

- **the project writer** — `factory.cli.init._project_writer`, bound to a
  recorder that still calls the real `container_manifest.write_project`, so the
  compose text quoted here is what the real renderer produced;
- **the compose runner** — `factory.cli.init._compose_runner`, which records the
  argv it is handed and returns exit 0 without running anything;
- and the seams `tests/test_ergane_init_check.bind_offline_seams` already closes
  for every full-init test: the forge, the control-plane probes and the schedule
  server.

The host is relocated off `~` (`HOME`, `XDG_CONFIG_HOME`, `ERGANE_STATE_HOME`),
which is why the paths are under `/tmp/pytest-of-unknown/...`. Sources:
`tests/test_init_container_reconcile.py` and `tests/test_container_supervisor.py`.

---

## 1. `ergane init .` regenerates the mount list

Before: the engine came up when only `alpha` was registered, so `widgets` is
mounted nowhere. The relevant fragment of the generated `compose.yaml`:

```yaml
    volumes:
      # State root: same absolute path here and in the engine, and the mount
      # that carries the engine's own Temporal database across a recreate.
      - .../state/ergane:.../state/ergane
      # Supervision home: a sibling of that database, not its parent.
      - .../state/ergane/supervision:.../state/ergane/supervision
      # Config directory: without it the engine's `~/.config` does not exist
      # and the persona registry resolves to the packaged example.
      - .../home/.config/ergane:.../home/.config/ergane
      # Registered repository, same-path so worktrees resolve on both sides.
      - .../alpha:.../alpha

# Per-repo same-path mount list. Re-run `ergane init <repo>` to add one.
x-ergane-repos:
  - source: ".../alpha"
    target: ".../alpha"
```

After `ergane init <…>/widgets` — the same file, same renderer, one more repo,
at its own path on both sides of every bind:

```yaml
      # Registered repository, same-path so worktrees resolve on both sides.
      - .../alpha:.../alpha
      # Registered repository, same-path so worktrees resolve on both sides.
      - .../widgets:.../widgets

x-ergane-repos:
  - source: ".../alpha"
    target: ".../alpha"
  - source: ".../widgets"
    target: ".../widgets"
```

## 2. …and reconciles the engine

Everything the compose-runner seam was handed, in full — one command, against
the project that was just regenerated. `up -d` reconciles rather than
duplicating, which is the whole of "the engine picks the repo up":

```text
('docker', 'compose', '-f',
 '/tmp/.../state/ergane/supervision/container/compose.yaml', 'up', '-d')
```

Nothing was stopped, removed or rebuilt: no `down`, `stop`, `rm` or `kill` verb
appears, and the test asserts their absence.

## 3. The reconcile line, in the report block

`ergane init` on a container-tier host, stdout verbatim (paths elided). The new
line sits directly under the registry row, because the two are halves of one
fact — the engine knowing this repo exists:

```text
joined /tmp/.../widgets as slug 'widgets'
written:
  /tmp/.../widgets/ergane.yaml
  /tmp/.../widgets/.gitignore
  /tmp/.../widgets/.ergane
registered: 'widgets' -> /tmp/.../widgets
engine container: regenerated /tmp/.../supervision/container/compose.yaml with
  /tmp/.../widgets mounted at its own path, and reconciled the engine
control plane: readable
schedule: created ergane-roadmap-widgets — created, starting roadmap-specs …
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
```

(The `engine container:` line is one line; it is wrapped here to fit the page.)

## 4. The same fact as a `--check` finding

Not a new output surface: it renders beside the twelve findings `ergane init
--check` already reports, through `gather_init_facts` and `run_check`. On the
host of §1 *before* init ran, with `widgets` registered and unmounted:

```text
  [FAIL] engine_container: the engine container project at
  /tmp/.../supervision/container does not mount /tmp/.../widgets at its own
  path, so the engine cannot see this repository — run `ergane init
  /tmp/.../widgets` to regenerate the mount list and reconcile the engine;
  without it the supervisor refuses at startup and a dispatch here finds no
  worktree
```

Exit code 1. After the init of §1–§3, the same check on the same host:

```text
  [PASS] engine_container: the engine container project at
  /tmp/.../supervision/container mounts /tmp/.../widgets at its own path
all 13 checks passed
```

## 5. A host with no engine container project is untouched

`installed_project()` returns `None` — the generated project on disk is the only
record that a host runs the container tier (plan R1) — so nothing is
regenerated, nothing is run, and nothing is said about a tier this host does not
have. Full stdout, and the two seams' recorded calls:

```text
joined /tmp/.../widgets as slug 'widgets'
written:
  /tmp/.../widgets/ergane.yaml
  /tmp/.../widgets/.gitignore
  /tmp/.../widgets/.ergane
registered: 'widgets' -> /tmp/.../widgets
control plane: readable
schedule: created ergane-roadmap-widgets — created, starting roadmap-specs …
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate

ergane readiness for /tmp/.../widgets (ergane.yaml)
  … 12 findings, no engine_container among them …
all 12 checks passed

compose argv: []   writes: []
```

Twelve findings here against thirteen in §4: the finding is *absent* on this
host rather than passing. A host with no container tier has not satisfied a
container requirement — it has no container requirement, and a `[PASS]` line
would teach an operator to expect one.

## 6. US6-S2: the supervisor's refusal names this verb

`_check_same_path_registry` refusing a registered repo whose recorded path is
not a directory (088 FR-009), driven directly with a scratch registry:

```text
repo 'widgets' is registered at /srv/widgets, which is not a directory
remedies: run `ergane init <repo path>` on the host, which regenerates the engine container's mount list with that repo at its own path and reconciles the engine; or, if the recorded path is stale rather than merely unmounted, rebuild the registry with `ergane repo rebuild <repo path> ...`
```

And the quote of it in `docs/container.md`, so the pair can be read as identical
in one place:

```text
remedies: run `ergane init <repo path>` on the host, which regenerates the
engine container's mount list with that repo at its own path and reconciles
the engine; or, if the recorded path is stale rather than merely unmounted,
rebuild the registry with `ergane repo rebuild <repo path> ...`
```

They differ only in line wrapping, and
`test_the_refusals_remedies_and_the_documented_ones_are_one_string` normalises
whitespace and nothing else to hold them to it. The remedy the refusal named
before this story — `ergane repo rebuild` alone — is kept for the case it always
addressed, a recorded path that is stale rather than merely unmounted, where no
mount would help because the registry is what is wrong.

## 7. The captures above are load-bearing

Removing the two call sites this story adds to `factory/cli/init.py` — the
`_reconcile_engine` call in the report block and `**_engine_facts()` in
`gather_init_facts` — and re-running the module:

```text
7 failed, 3 passed in 0.64s
FAILED test_init_adds_the_new_repo_to_the_mount_list_and_reups_the_engine
FAILED test_the_reconcile_is_reported_as_one_line_beside_the_registration
FAILED test_a_hand_edited_project_is_reported_rather_than_silently_not_regenerated
FAILED test_the_declined_confinement_survives_a_reconcile
FAILED test_check_fails_when_the_engine_does_not_mount_this_repo
FAILED test_check_passes_once_init_has_reconciled_the_engine
FAILED test_check_reports_an_unreadable_project_rather_than_crashing
```

The three that survive are the ones that must: two assert that a host with no
engine container project behaves exactly as it did before this story, and one is
the detonator that fails if a test ever reaches the real compose runner. A
mutation those three noticed would mean they were asserting the wrong thing.
