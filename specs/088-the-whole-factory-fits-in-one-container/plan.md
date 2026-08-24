# Implementation Plan: the whole factory fits in one container

**Spec**: `specs/088-the-whole-factory-fits-in-one-container/spec.md`
**Evidence base**: `docs/container-onramp-research-findings.md` — the measured
answers this plan leans on. Where a trap below says "measured", that document's
§1 appendix is the experiment log.

## What already exists, and where

**Every line number below was read individually off `838b9c3`** (2026-08-22,
re-confirmed 2026-08-23; the tree has not moved). Check each anyway before you
edit — a plan citing a moved anchor sends you hunting at the operator's
expense.

**US1 — the probe you are fixing (`factory/controlplane/verify.py`):**

- `factory/controlplane/verify.py:253` — `def _inspect_host() -> dict[str,
  Any]:` — the *only* place this module touches the real host, by its own
  docstring. Everything it returns is plain data so `HostProbe.evaluate` stays
  pure. Keep that property: your execution goes here, its result goes into
  the returned dict, and no judgement moves into `evaluate`.
- `factory/controlplane/verify.py:261` — `bwrap_path = shutil.which("bwrap")`
  — discovery. This stays; it is what `present` means.
- `factory/controlplane/verify.py:280-285` — the `"bwrap"` entry. `:281` is
  `"present": bwrap_path is not None,` and `:282` is `"usable": bwrap_path is
  not None,` — **the same expression twice. That is the defect.**
- `factory/controlplane/verify.py:284` — `"remedy": "install bubblewrap
  (bwrap)"` — the absent-case remedy. FR-003 wants a second one, textually
  distinct, naming `container/seccomp-ergane.json` and
  `container/ergane-engine.profile` by path.
- `factory/controlplane/verify.py:249-250`, `:265-275` — the GitHub CLI entry:
  `shutil.which`, then `subprocess.run(..., timeout=5)` with
  `except (subprocess.TimeoutExpired, OSError)`. **This is the shape to
  copy** — gh already separates "found the binary" from "the binary
  answered"; bwrap is the one that does not. And `:292-298` — the gh entry
  carries *two* remedy keys (`absent_remedy` `:296`,
  `unauthenticated_remedy` `:297`): the precedent for FR-003's second remedy,
  eleven lines below the entry you are fixing.

**US1 — the two consumers that make it matter (read, do not edit):**

- `factory/workgraph/adapter.py:288` — `BWRAP_BACKEND_BINARY =
  Path("/usr/bin/bwrap")`, and `factory/verify/gates.py:138` — the same
  literal. The pin is deliberate (`factory/workgraph/adapter.py:285-287`):
  only the system path carries an AppArmor grant. **Probe that path, not
  `shutil.which`'s answer.**
- `factory/workgraph/adapter.py:622-628` — `BwrapBackend.launch` refuses on
  `not binary.is_file()` — file existence only. A present-but-blocked bwrap
  sails past and dies at `create_subprocess_exec` (`:643`). You are not
  changing this; the preflight catches what it cannot.
- The mount set the probe must imitate: `factory/verify/toolchain.py:203`
  (`system_tree_argv`) with `/usr` read-only at `:251`, and the adapter's
  worktree bind at `factory/workgraph/adapter.py:477-478`. The probe argv
  wants the *shape* — ro `/usr`, `--proc`, `--dev`, a tmpfs — not the full
  agent argv.

**US2 — the children you supervise, all three already landed:**

- `factory/supervision/temporal_server.py:68` — `def main(argv)` with
  `--db-filename` **required** (`:73-77`), `--namespace` defaulting to
  `ergane` (`:78-82`), `--ip` defaulting `127.0.0.1` (`:83-87`), `--port`
  defaulting `7233` (`:88-93`). Blocks forever (`:54-55`), shuts down in a
  `finally` (`:56-57`).
- `factory/worker.py:1` — run as `factory.worker`.
- `factory/notify/service.py:1` — run as `factory.notify.service`.
- `factory/supervision/units.py:115-119` — `_MODULES`, the existing
  unit-name→module mapping. **The precedent for FR-005's "declared in one
  place"** — same shape, not the same object; systemd's mapping and the
  container's are different facts that happen to agree today.
- `factory/supervision/temporal_server.py:9-12` — why no child argv may
  contain `python -`: a 2026-08-12 cleanup sweep ran `pkill -f "python -"`
  and matched the worker's own command line.

**US2 — the registry FR-009 reads (`factory/registry.py`):**

- `:375` `load_registry` — call with no argument; it resolves its own path.
- `:181` `resolve_registry_path`, `:159` `resolve_state_home` — honours
  `ERGANE_STATE_HOME`; the container relocates the state home, so never
  hardcode.
- `:243-250` `RegistryEntry` — `slug` `:247`, `path` `:248` (the recorded
  absolute location FR-009 checks).
- `:253-258` `Registry.entries` at `:258`.
- `:266-271` `for_path` resolves before comparing (`:267`) — follow that, or
  a symlinked mount reads as a mismatch.
- `:119-128` `RegistryCorrupt` — "it is a cache — re-derive it with `ergane
  repo rebuild ...`" (`:126-127`). **The registry is a derived cache**; the
  refusal names both remedies (wrong mount, stale cache).

**US3 — what the image and artifacts must contain, derived not invented:**

- Binaries: `factory/controlplane/verify.py:261-263` (bwrap, git, gh) plus
  `factory/workgraph/adapter.py:398-401` — `resolve_toolchain((self.executable,
  UV, NODE, GIT), ...)` with `DEFAULT_EXECUTABLE = "claude"` at `:97`. All
  four required; dispatch refuses by name when one is missing.
- `/usr` is read-only in the sandbox (`factory/verify/toolchain.py:203`,
  `:251`) — the image, not the gate, carries the toolchain.
- The confinement artifacts' required content is specified in the findings
  appendix: seccomp = vendored moby default (record its version) + the seven
  syscalls unconditionally allowed + the `clone3` ERRNO rule removed;
  AppArmor = docker-default template + `userns,`/`mount,`/`pivot_root,` with
  every deny retained, `abi <abi/4.0>` declared, profile name
  `ergane-engine`. Copy the text from the findings appendix; do not
  re-derive it from upstream at implementation time.
- The reference compose's required keys are FR-012's list. The supervision
  home and state root resolve through `factory/registry.py:159`'s state-home
  logic and the supervision layout — find the supervision home's resolver in
  `factory/supervision/` and cite the real path variables in the file rather
  than inventing names.

**US4 — the verbs (`factory/cli/nouns/worker.py`):**

- `:29-33` `_install`, `:41-45` `_migrate`, `:48-56` `_deploy`.
- `factory/supervision/units.py:716` `install`, `:107` `ENABLE_TARGETS`.
- `factory/cli/install.py:815-833` — `_systemd_user_session_available()`;
  docstring at `:818-819` names containers. **Reuse this predicate; do not
  write a second one.** Moving it somewhere both callers import is fine.

## Traps

**1. The probe must execute the pinned path, not the discovered one.**
`shutil.which("bwrap")` may answer with a different binary than
`/usr/bin/bwrap`, and only the pinned one is what dispatch uses
(`factory/workgraph/adapter.py:285-288`).

**2. The probe must exercise the production mount shape.** Measured (findings
failure mode 14): `bwrap --ro-bind / / true` passes on kernels where the
production `--proc` mount is refused. A probe that under-mounts reports green
where dispatch fails. Shape: ro-bind `/usr`, `--proc /proc`, `--dev /dev`, a
tmpfs, then exit. Bounded timeout, `check=False`,
`except (TimeoutExpired, OSError)` — the gh check's discipline at
`factory/controlplane/verify.py:265-275`.

**3. The probe must not be PID 1 and must not assume root works.** Measured:
as container PID 1 bwrap fails `setting up uid map: Permission denied`
(findings failure mode 2), and as uid 0 it takes a `clone(CLONE_NEWNS)` path
that needs `CAP_SYS_ADMIN` (failure mode 1). The probe runs bwrap as an
ordinary subprocess of the CLI process (never as a container entrypoint), and
`docs/container.md` records that the engine runs non-root — the probe does
not need to special-case root, but its remedy text should name "running as
root inside a container" as a cause when the uid is 0.

**4. `_inspect_host` returns data; `evaluate` stays pure.** The module's own
docstring (`factory/controlplane/verify.py:4`) declares the split. Exec in
`_inspect_host`, verdict in the returned dict.

**5. Skip by guard, never by marker.** FR-004's real-binary test runs only
where bwrap actually executes; the guard is a real check at call time. This
repo has been bitten by marker-skips that covered nothing.

**6. Do not start real children in the supervisor's tests.** This host was
OOM-killed once by test-spawned orphans; the three real children are a
Temporal server, a Temporal worker and a Telegram bridge. Stubs only; if a
live process is unavoidable, `sleep`-shaped and reaped in a `finally`.

**7. The readiness wait is bounded and names what it waited for** (address
and timeout, in the message). An unbounded wait turns a misconfigured address
into a container that starts, prints nothing and never works.

**7a. An empty registry is a fresh container, not a fault.** Zero entries and
an absent registry file both start normally — the first bring-up happens
before any `ergane init`.

**7b. Resolve before you compare, and name both remedies** (wrong mount /
stale cache — `factory/registry.py:266-271`, `:126-127`).

**8. You cannot build the image you are writing.** No docker socket inside
bwrap. US3's criteria are drift tests over committed text, red before green.
Do not fake a build log; do not add a gate that shells out to docker.

**9. The drift tests derive, never restate.** Binary names come from the
probe and the toolchain resolution; the seccomp allow-list assertion reads
the seven-syscall set from one declared constant the test and the artifact
comment share. A hand-copied list passes forever after someone edits
`_inspect_host`.

**10. Copy the confinement artifacts from the findings appendix; do not
regenerate from upstream.** The moby default profile moves between releases
(findings failure mode 8). The committed files carry a comment naming their
upstream base and version; regeneration is a deliberate future act, not an
implementation-time convenience.

**11. No `unconfined` token in any committed artifact.** The whole point of
config G is that the compose a developer inspects reads as a named, narrower
contract. FR-012's drift test asserts the absence; do not "temporarily" add
`apparmor:unconfined` to make something pass — if the profile is missing on
the host, that is 104's install-time problem, not this spec's.

**12. Reuse `_systemd_user_session_available`.** Two predicates is how the
refusal and the interview stop agreeing.

**13. The judge sees the diff and the criteria, nothing else** (Principle
VIII). Every SC is pasted-output; the pastes are committed in the diff or the
criterion is unprovable.

## Sizing

US1 grew one scenario (the argv-shape test) but remains small: one dict
entry, one injectable exec, four tests. US2 is the largest — a supervisor
with signal handling, a readiness wait and the registry check — but ordinary
process supervision, all stub-tested. US4 is the smallest.

**US3 is the one that will cost a second attempt if dispatched loosely.** It
now ships four artifact families (Dockerfile, two confinement files,
reference compose) plus docs, all drift-tested, none executable by the
implementer. Traps 8–11 are its whole survival kit. The artifact *content* is
not a design task — the findings appendix has the text; the story's work is
committing it faithfully and pinning it with tests that would catch a
regression.

## What else is in flight, and why it does not collide

Specs 087 and 099 are at draft; neither names
`factory/controlplane/verify.py`, `factory/cli/nouns/worker.py`, `container/`
or a new module under `factory/supervision/`. Specs 103–106 (the rest of the
onramp program, `docs/container-onramp-program.md`) are sequenced *around*
this one: 103 touches the installer and scanner only; 104 consumes what this
spec commits and must not start until it lands; 105 edits the release
workflow and the supervisor's version reporting afterwards.

099 is worth reading for a non-collision reason: in a container the recreate
is the deploy, so its restart-safety is load-bearing on this path.

## Verification the operator will run, independent of the gate

- **Build the image, run the preflight from inside**: the container-run
  `ergane install --verify` must report bwrap **usable** under the reference
  compose's exact options. If it reports unusable, US1 worked — read the
  remedy.
- **The confinement matrix is already measured** — do not re-litigate it at
  verification time; the two open confirmations (x86_64, stock noble) live in
  the program document and are not gates on this spec.
- **Measure the dev-server download** (network-blocked run) and record the
  answer in `docs/container.md`.
- **Break the mount on purpose**: change one repo's mount target, confirm
  FR-009 refuses by slug before any child starts.
- **Join a second repo** and confirm the list shape holds.
- **Run one real node end to end inside the container** against a scratch
  repo with `gh` authenticated, and watch it reach a verdict and land. This
  is the run that makes the container real.
