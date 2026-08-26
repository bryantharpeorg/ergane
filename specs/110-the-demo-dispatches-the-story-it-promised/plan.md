# Implementation Plan: the demo dispatches the story it promised

Drafted 2026-08-26 against ergane-buildout at 4aae6b7. Every anchor below was
read from that commit. The measured facts in spec.md's frontmatter (the bwrap
probe, the missing config) are inputs to this plan, not open questions.

## Requirements, numbered here

- **FR-001** — With `ERGANE_DEMO=1` in the environment and no sentinel, the
  supervisor spawns the demo driver as a plain subprocess after worker and
  bridge are started (`container_supervisor.py:334-336`). The driver is never a
  member of `_CHILDREN` (`:39-43`) nor of the `controllers`/`tasks` maps
  (`:338-347`); its exit — zero or not — never stops the container. Without
  `ERGANE_DEMO=1`, nothing is spawned and the supervisor's behaviour is
  byte-for-byte today's.
- **FR-002** — The driver's prepare phase performs, in order: (1)
  `ergane install --from-file /opt/ergane/container/ergane-install-answer.demo.toml`;
  (2) `git init -b main` of the demo repository; (3) the manifest, with the
  same text `_demo_manifest_text` returns (`factory/cli/install.py:1049-1056`),
  written via `init_module._write_scaffold` as `_closing_demonstration` does
  (`:1001`); (4) the spec trio from `scaffold_spec(slug="demo",
  title="Demonstration", anchor=…, demonstration=True)`
  (`factory/doctor/scaffold.py:27-66`) written under `specs/001-demo/`; (5) one
  git commit of all of it. Each step that is expressible as an `ergane` verb is
  run as that verb; the driver imports no factory internals beyond the two
  named seams.
- **FR-003** — The commit is made under an explicit demo identity (git
  `user.name`/`user.email` set for the repo, never assumed from the
  environment); the container user has no global git identity and must not
  need one.
- **FR-004** — After prepare, `ergane spec validate specs/001-demo
  --target-repo <repo>` and `ergane spec derive …` both succeed. The committed
  test proves it through the CLI seam (`_run_cli`,
  `factory/cli/install.py:1071-1075`) and asserts `workgraph.json` exists.
- **FR-005** — Before any dispatch, the driver probes an adapter-shaped bwrap
  invocation: `--die-with-parent --unshare-pid --proc /proc --dev /dev` plus
  read-only binds of the toolchain roots, the shape assembled at
  `factory/workgraph/adapter.py:427-580`. On refusal it prints the probe's
  stderr verbatim, one named remedy line, stops before dispatch, and the
  supervised services keep running — and the committed test **asserts the
  keep-running part directly through the supervisor seam** (three children
  still up after the driver exits nonzero), not by inference from a missing
  sentinel. The probe must include `--proc`: the measured failure
  (`bwrap: Can't mount proc`) fires there and nowhere earlier.
- **FR-006** — First boot happens at most once, with **two sentinels carrying
  two different promises**, both under `$ERGANE_STATE_HOME/demo/`:
  `prepared` is written only **after the sandbox probe succeeds**, so a probe
  refusal leaves no sentinel and a restart retries the probe (a stranger who
  fixes their host by restarting gets the demo); `dispatch-attempted` is
  written immediately **before** `build ship` (FR-009), so no crash window
  re-spends the key. Writing one sentinel for both promises collapses
  "retryable host problem" into "money was spent", and the first run's judge
  refused exactly that collapse.
- **FR-007** — The dispatch is exactly one verb: `ergane build ship
  specs/001-demo --target-repo <repo> --yes --halt-after-pass`. `build ship`
  already chains validate → derive → confirm → dispatch
  (`factory/cli/nouns/build.py:838-893`), takes `--yes` (`:1729-1733`), and
  carries `--halt-after-pass` because `add_landing_dial_flags` declares it
  (`factory/cli/landing.py:183-191`) and `ship_command` delegates to
  `start_command` (`build.py:893`), which reads it via
  `halt_after_pass_from_args` (`landing.py:203-209`). The driver assembles
  this argv and nothing else.
- **FR-008** — The driver watches the epic by polling `ergane build status
  001-demo` and prints each node-state transition once as observed. On a
  terminal state it prints the full status render, which in halting mode
  carries the landing-not-attempted statement — `_halt_after_pass_lines`
  (`build.py:557-572`), appended to the render at `build.py:468`. The
  statement reaches the compose log stream verbatim; the driver adds no
  paraphrase.
- **FR-009** — A nonzero `build ship` (preflight finding from `_run_preflight`
  (`build.py:738-746`), unresolvable proxy from `_resolved_proxy_url`
  (`build.py:692-720`), refused persona) is printed as the driver's last words;
  the dispatch sentinel is written so a restart does not retry the spend; the
  driver exits nonzero; the services stay up.
- **FR-010** — A dispatched epic that fails its gate or judge is reported with
  the failure render exactly as `build status` states it. The mode changes
  where success stops, never what failure means (109 US3-S4, FR-016 there).
- **FR-011** — `container/compose.demo.yaml` gains, in the engine service's
  `environment` list (`:33`), the literal entries `ERGANE_DEMO=1` and
  `LITELLM_PROXY_URL=http://gateway:4000`. The mandatory-count test
  (`tests/test_109_us2_demo_compose.py:275-289`) still counts exactly one:
  literals have no `${…}` form and `_is_mandatory` (`:181`) cannot match them.
- **FR-012** — The engine service's `security_opt` (`:20-32`) gains
  `systempaths=unconfined`, with a comment in the voice of the existing
  seccomp/apparmor block (`:22-30`) naming the mechanism: Docker's masked
  /proc paths trip the kernel's fully-visible-proc refusal when bwrap mounts
  a fresh procfs in its user namespace (bubblewrap#284); measured on kernel
  6.17.0-1018 on 2026-08-26; without it the agent sandbox cannot start.
- **FR-013** — Nothing else in the file changes: services, volumes, mounts,
  configs and the mandatory variable are all as 109 landed them, proven by the
  existing drift suite passing unmodified except the tests this story extends.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| The whole prepare sequence, minus the commit | `_closing_demonstration`, `factory/cli/install.py:972-1038` | Runs in a tempdir on the interactive path; stops at derive **on purpose** (program doc decision 7 — install must stay free) |
| Manifest text (`runtime: bwrap`, echo gate) | `_demo_manifest_text`, `install.py:1049-1056` | The gate is `echo demonstration gate` — deterministic and free |
| One-shot git init | `_git_init`, `install.py:1041-1046` | No identity, no commit — the demo driver needs both |
| Demonstration spec generator | `scaffold_spec(demonstration=True)`, `factory/doctor/scaffold.py:27-66` | "the worked story alone, no sentinel, no skeletal slots, so a throwaway spec can be derived cleanly" |
| Non-interactive install | `ergane install --from-file`, `install.py:912`, `_install_from_file` `:1232` | Validates, seeds personas, writes config under the lock; the bundled answers file `container/ergane-install-answer.demo.toml` declares `gateway_mode = "managed"`, `base_url = "http://gateway:4000"` |
| One-verb dispatch with halt | `ergane build ship`, `build.py:838-893`, flags `:1680-1735` | `--yes --halt-after-pass` both ride today |
| Halt statement | `_halt_after_pass_lines`, `build.py:557-572`, appended `:468` | Renders only from `build status`/start output — which is exactly why the driver polls status |
| Status verb | `build.py:1736-1744` | `epic_id` is the spec directory's name: `001-demo` |
| Proxy resolution, env route | `resolve_proxy_url`, `factory/controlplane/resolve.py:168-187` | env `LITELLM_PROXY_URL` first, config second — the demo will have **both** after US1+US3 |
| Persona chain | deriver default `IMPLEMENTER` (`factory/workgraph/derive.py:86`) → `container/personas.demo.yaml:18-19` (`implementer`, agent `claude-code`, model `demo/implementer`) → inline gateway config → `os.environ/UPSTREAM_MODEL_API_KEY` | Closed end to end; nothing to add |
| Supervisor spawn seam | `container_supervisor.py:334-336` (worker+bridge just started), injectable `start_child` for tests (`:260-272`) | `main()` logs bare messages (`:497`), so driver lines print clean in `docker compose up` |
| Compose env + security blocks | `container/compose.demo.yaml:20-32` (security_opt), `:33-68` (environment) | The three US3 lines slot into these two lists |

## Technical approach, story by story

### US1 — first boot leaves the demo project dispatchable

New module `factory/supervision/demo_driver.py` with a `main()` and a
`python3 -m` entry, mirroring the supervisor's own conventions (no `python -`
substring in argv — the file's opening docstring explains why). Phases are
functions taking explicit paths (state home, repo root, answers file) so tests
drive them against scratch directories with no container, no Temporal, no
gateway. The prepare phase shells `ergane install --from-file` and then
reproduces `_closing_demonstration`'s repo steps against the *persistent* repo
path instead of a tempdir, adds the git identity and the commit, runs the
sandbox probe, writes the sentinel. The supervisor change is small: after
starting worker and bridge, if `ERGANE_DEMO=1`, spawn
`python3 -m factory.supervision.demo_driver` with a reaping task whose failure
is logged and never fatal.

### US2 — the demo dispatches, narrates, and halts

Second phase of the same module. Assemble the `build ship` argv (FR-007), run
it with output streaming through, then poll `build status --json` on an
interval, diffing node states, printing transitions, and finishing with the
human render (FR-008). The seam between "run a CLI verb" and the phase logic is
one injectable callable, so the committed tests script sequences (refusal;
PASSED; gate-failure) without any real dispatch.

### US3 — the file carries the demo

Three lines in `container/compose.demo.yaml` (two env literals, one
security_opt entry with its mechanism comment) and the extensions to the 109
drift suite that pin them: presence, literalness, the unchanged mandatory
count, and the systempaths comment naming bubblewrap#284.

## Traps

**T1 — the driver must not be a supervised child, and the reason is fatal.**
The supervisor treats any child dying unprompted as a fault and stops the
container naming it (`container_supervisor.py:420-426`). A one-shot in
`_CHILDREN` means every successful demo kills the stack at the moment of
success. Spawn it as a plain subprocess, reap it in a task whose result is
logged, never joined into the fatal set.

**T2 — do not run the driver in-process on the supervisor's event loop.** The
109 attestation records exactly this class of failure: `drift_for_spec`
shelled git on the worker's event loop, starved a heartbeat for 5m12s, and an
infrastructure kill ate a 138-insertion attempt. The driver blocks on installs,
git, and a long watch loop. It is a subprocess; the supervisor only reaps it.

**T3 — the repo needs a commit, and the container user has no git identity.**
`_closing_demonstration` never commits because derive reads the working tree;
dispatch creates worktrees from `main` and an empty branch dispatches nothing.
`git -C <repo> -c user.name=… -c user.email=… commit` (or repo-local config) —
never rely on a global identity that does not exist. This is a
first-attempt-killer of the same species as 109-US2's three attempts.

**T4 — two sentinels, and their order is the design.** The `dispatch-attempted`
sentinel goes down *before* `build ship` — a crash between dispatch and
sentinel re-spends the stranger's key on restart, and a demo that quietly
bills twice is the rejected outcome. The `prepared` sentinel goes down only
*after* the sandbox probe succeeds — a probe refusal must leave **no**
sentinel, so a restart retries a host problem the stranger may have just
fixed. This epic's first us1 run was judge-FAILED for writing the first-boot
sentinel before the probe (restart became a no-op instead of a retry) and for
proving "services stay up" only by the absence of a sentinel. Both halves are
now FR-005/FR-006 obligations; do not re-merge the sentinels for tidiness.

**T5 — the sandbox probe must include `--proc`, or it lies.** The measured
failure fires at the fresh procfs mount inside the namespace, after every
earlier step succeeds. A probe of `bwrap true` without `--unshare-pid --proc`
passes on a host where the real sandbox cannot start. Mirror the adapter's
shape (`adapter.py:427-580`), assert on its stderr.

**T6 — two persona registries exist in the container; only one is the
engine's.** `_install_from_file` seeds an XDG-path registry
(`install.py:1261-1268`) as a side effect; the engine reads
`ERGANE_PERSONAS_PATH=/opt/ergane/container/personas.demo.yaml`
(`compose.demo.yaml:66`). Do not "fix" the driver to point the engine at the
seeded one — the demo registry is the one whose aliases the bundled gateway
serves (109's T2: the `example/` refusal is the specification).

**T7 — the compose env additions must be literals.** The mandatory-count test
(`test_109_us2_demo_compose.py:275-289`) counts `${…}`-without-default forms.
`ERGANE_DEMO=1` and `LITELLM_PROXY_URL=http://gateway:4000` as literals keep
the count at one. Writing either as `${ERGANE_DEMO:?}`-style breaks FR-011 and
109's FR-009 at once.

**T8 — driver tests run against seams, never against live processes.** No test
may start a real Temporal, worker, or gateway: the suite already carries the
scar tissue of 8,131 orphaned test servers OOMing the host. The injectable
CLI-runner callable and scratch directories are the whole test surface.

**T9 — do not implement a forge, still.** 109's T8 stands verbatim. The demo
ends at PASSED with the statement; a "tiny local forge to finish the story" is
the rejected design, twice now.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
  depends_on: []
US2:
  implements: [FR-007, FR-008, FR-009, FR-010]
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: [FR-011, FR-012, FR-013]
  depends_on: []
  concurrent_with: [US1, US2]
```

Chain depth 2 — US1 → US2, with US3 alongside from round one.

## Sizing

Three stories. US1 is the largest: one new module's prepare phase, one small
supervisor change, and the offline tests that drive both. US2 is the same
module's second phase against a scripted seam. US3 is three lines and their
drift tests.

**US1 is the one at risk of sprawl.** Its unit of value is "a dispatchable
project exists and the sandbox is proven" — not "a framework for demos".
Resist configuration surface (no flags beyond `ERGANE_DEMO`, no alternate
repos, no pluggable specs). Those are separate specs if they are anything.

## File contention

| story | owns |
| --- | --- |
| US1 | `factory/supervision/demo_driver.py` (new), `factory/supervision/container_supervisor.py`, `docs/decisions.md` (one appended entry), its tests (new file) |
| US2 | `factory/supervision/demo_driver.py` (dispatch/watch phase), its tests |
| US3 | `container/compose.demo.yaml`, `tests/test_109_us2_demo_compose.py` |

US1 and US2 share the module by design and are strictly sequential
(`depends_on_merged`). US3 shares nothing with either; it is named in their
prose only, which is why `concurrent_with` is declared.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; the committed artifact carries compile-time absolute
  paths.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**
  `tests/test_ergane_install_closing_step.py:450` asserts no
  `/tmp/ergane-*` directory contains `specs/`; a concurrent operator gate
  turns a node's gate red for a reason the node cannot see. Measured twice on
  2026-08-25.
- **US1 lands a `docs/decisions.md` entry.** The log is append-only by
  construction; the entry supersedes nothing and narrows nothing — it records
  the decision-7 boundary (install's demonstration stays free; the compose
  demo's exported key is the spend opt-in, taken 2026-08-26).
- **The worker on the floor host must be current before dispatch** — a stale
  worker imports stale factory code when a story lands.

## Verification the operator will run, independent of the gate

After this epic lands and before the release is cut: build the image from the
landed head, then on this host

```bash
ERGANE_VERSION=<local tag> UPSTREAM_MODEL_API_KEY=… \
  docker compose -f container/compose.demo.yaml up
```

and watch one first boot end to end: install transcript, scaffold, `build
ship`, agent, gate, judge, and the halt statement, all in the compose stream.
Then restart the stack and watch the driver say it has already run. The
released-asset rerun on a machine that has never had Ergane stays the closing
evidence, exactly as 109 wrote it.
