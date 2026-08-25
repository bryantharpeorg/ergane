# 104-US7 — uninstall unplugs the engine container: a seam capture

**This is a seam capture, not a run against a daemon.** Every transcript below
is the output of `run_teardown` driven through injected seams — the **process
runner** `TeardownRequest.run` (`factory/cli/uninstall.py:106`, the parameter
`uninstall()` already had, which now also carries `docker compose`) and the
**step table** seam of `run_teardown` (`:803`), which the `--check` evidence in
`tests/test_teardown_owns_the_ordering.py` replaces wholesale. No Docker daemon
exists in this environment and none was contacted: the agent sandbox binds no
`/var/run/docker.sock`, and trap 11 forbids starting a real daemon, container or
`apparmor_parser`. **The `docker compose … down` lines below are argv the
recording runner captured, not a container that stopped.** Temporal, systemd and
the schedule server are the same fakes 083's suite already drives.

The real runs against a real daemon are the operator's, in the last section of
this spec's `plan.md`; no gate waits on them. Captured by
`tests/test_teardown_container_step.py`'s fixtures on 2026-08-25; `/tmp/…/`
elides one pytest tmp path prefix and `~` one home, and nothing else is edited.

The host in every capture: dispatch running under a schedule, one registered
repository, six installed systemd units, an engine container project written by
US3's writer, **and one file the operator put in that project directory by
hand** (`docker-compose.override.yaml`). That last file is the whole control on
"removes what install generated — and nothing else".

## 1. `--check` — the six-step plan, performing none of it (US7-S1)

The engine container is step **3** (R9): dispatch is paused first, the
repositories are forgotten second, and the engine has to be down before `clear
state` could empty a directory it is writing to. That insert renumbers every
step after it — `stop and remove units` reads `4/6` where it read `3/5`
(trap 12).

```text
teardown plan, 6 steps in the order the table declares; --check performs none of them:
1/6 pause dispatch: pause dispatch for /tmp/…/widgets/specs (schedule ergane-roadmap-widgets)
2/6 forget repositories: forget 1 registered repository: widgets
3/6 stop the engine container: take the engine container down from /tmp/…/state/supervision/container/compose.yaml and remove the 4 file(s) this engine wrote under /tmp/…/state/supervision/container: .env, compose.yaml, ergane-engine.profile, seccomp-ergane.json
    kept: /tmp/…/state-home/ergane (the state root; this step removes nothing outside the engine container's own project directory)
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
4/6 stop and remove units: stop and remove 6 file(s) this engine wrote, under /tmp/…/home/.config/systemd/user and /tmp/…/state/supervision
5/6 clear state: nothing to do: --purge was not given, so nothing under /tmp/…/state-home/ergane is removed; the config at /tmp/…/config/ergane/config.toml is kept either way
    kept: /tmp/…/state-home/ergane/doctor.db (state; --purge removes it)
    kept: /tmp/…/state-home/ergane/repos.json (state; --purge removes it)
    kept: /tmp/…/state-home/ergane/repos.json.lock (state; --purge removes it)
    kept: /tmp/…/state-home/ergane/worktrees (state; --purge removes it)
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
    kept: /tmp/…/config/ergane/offline-control-plane.toml (beside the config, so treated as a secret)
    kept: /tmp/…/config/ergane/telegram.env (beside the config, so treated as a secret)
    ERGANE_STATE_HOME is set, so the emptied root would be /tmp/…/state-home/ergane; ~/.local/state/ergane is the root this host would use without it, and teardown does not empty it
6/6 account for git refs: nothing to do: 2 branch(es) under refs/heads/factory/ and 2 ref(s) under refs/salvage/ stay, across 1 repository; --scrub-refs removes them
    /tmp/…/widgets: 2 under refs/heads/factory/, 2 under refs/salvage/
    list them yourself, one namespace each:
    git for-each-ref refs/heads/factory/
    git for-each-ref refs/salvage/
--check performed none of it: nothing was written, removed, stopped or signalled
```

The survey names the engine and every file it would remove, and it performed
none of it — asserted directly, in the same run
(`test_check_names_the_engine_and_the_files_and_performs_nothing`):

```text
host.events == []                                     # the shared runner log: no docker, no systemctl, no schedule call
sorted(p.name for p in directory.iterdir()) == before  # .env, compose.yaml, ergane-engine.profile, installed.json, seccomp-ergane.json, docker-compose.override.yaml
json.loads((directory / "installed.json").read_text())["files"]  -> truthy: the manifest still claims all four
```

## 2. The real run — the engine down, the project gone, everything else kept (US7-S1)

Steps 1–2 and 4–6 are 083's and are elided to the one this story adds. Note the
last two lines of the block: a file the manifest never claimed is the
operator's, and the directory still holding it is not teardown's to remove
either. That is provenance by digest rather than a filename allow-list.

```text
3/6 stop the engine container: take the engine container down from /tmp/…/state/supervision/container/compose.yaml and remove the 4 file(s) this engine wrote under /tmp/…/state/supervision/container: .env, compose.yaml, ergane-engine.profile, seccomp-ergane.json
    kept: /tmp/…/state-home/ergane (the state root; this step removes nothing outside the engine container's own project directory)
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
    took the engine container down: docker compose -f /tmp/…/state/supervision/container/compose.yaml down
    removed: /tmp/…/state/supervision/container/.env
    removed: /tmp/…/state/supervision/container/compose.yaml
    removed: /tmp/…/state/supervision/container/ergane-engine.profile
    removed: /tmp/…/state/supervision/container/seccomp-ergane.json
    kept: /tmp/…/state/supervision/container/docker-compose.override.yaml (not written by ergane)
    kept: /tmp/…/state/supervision/container (it still holds files ergane did not write; --purge takes them)
```

The one event log every fake in this suite shares, in the order it was written —
this is the whole of "the engine goes down", and it is argv, not a container:

```text
('pause', 'ergane-roadmap-widgets')
('delete', 'ergane-roadmap-widgets')
('docker', 'compose', '-f', '/tmp/…/state/supervision/container/compose.yaml', 'down')
('systemctl', '--user', 'disable', '--now', 'ergane-bridge.service')
('systemctl', '--user', 'disable', '--now', 'ergane-probe.timer')
('systemctl', '--user', 'stop', 'ergane.slice')
('systemctl', '--user', 'daemon-reload')
```

`docker compose … down` sits after the two Temporal acts and before the first
`systemctl`, which is R9 asserted on the acts rather than on the sentences
printed about them. And the filesystem afterwards, read by the test rather than
described (`test_the_step_takes_the_engine_down_and_removes_what_install_generated`,
`test_a_file_the_operator_wrote_into_the_project_directory_survives`):

```text
directory.exists()                                -> False   # on the host with no hand-added file
(state_home / "doctor.db").read_text()            -> 'seeded\n'
config.is_file(), secret.is_file()                -> True, True
(directory / "docker-compose.override.yaml").read_text()
                                                  -> '# my own override, please keep\nservices: {}\n'
```

## 3. `--purge` — the same artifacts, each removal named (US7-S2)

083's purge semantics extended to the generated artifacts. In the default layout
`project_dir` is under `supervision_home()`, which is under the state home step
5 empties — so those bytes were going regardless, in one `shutil.rmtree` that
names nothing. The extension is therefore less "remove more" than *name* it: one
labelled line per path, in the step that owns the engine container, including
the operator's own file and the directory itself. The plan half says so before
it happens.

```text
3/6 stop the engine container: take the engine container down from /tmp/…/state/supervision/container/compose.yaml and remove the 4 file(s) this engine wrote under /tmp/…/state/supervision/container: .env, compose.yaml, ergane-engine.profile, seccomp-ergane.json; --purge takes whatever else that directory holds
    kept: /tmp/…/state-home/ergane (the state root; this step removes nothing outside the engine container's own project directory)
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
    took the engine container down: docker compose -f /tmp/…/state/supervision/container/compose.yaml down
    removed: /tmp/…/state/supervision/container/.env
    removed: /tmp/…/state/supervision/container/compose.yaml
    removed: /tmp/…/state/supervision/container/ergane-engine.profile
    removed: /tmp/…/state/supervision/container/seccomp-ergane.json
    removed: /tmp/…/state/supervision/container/docker-compose.override.yaml
    removed: /tmp/…/state/supervision/container
```

The five state paths and the config keep 083's own labels in the same run, two
steps later — purge is not this step widening its remit past what it owns:

```text
5/6 clear state: remove 4 entries under /tmp/…/state-home/ergane and 1 lock file beside /tmp/…/config/ergane/config.toml; the config itself is kept
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
    kept: /tmp/…/config/ergane/offline-control-plane.toml (beside the config, so treated as a secret)
    kept: /tmp/…/config/ergane/telegram.env (beside the config, so treated as a secret)
    removed: /tmp/…/state-home/ergane/doctor.db
    removed: /tmp/…/state-home/ergane/repos.json
    removed: /tmp/…/state-home/ergane/repos.json.lock
    removed: /tmp/…/state-home/ergane/worktrees
    removed: /tmp/…/config/ergane/config.toml.lock
```

`test_purge_extends_to_the_generated_artifacts_and_names_every_removal` asserts
the `removed` and `kept` sets in the engine block are disjoint and both
non-empty, which is the FR-013 shape a removal-only assertion cannot see.

## 4. The daemon is not there — reported, not raised (trap 13)

`factory/cli/nouns/worker.py:30` refuses three verbs without a systemd user
session and `_uninstall` (`:49`) deliberately does not call it, because removal
has to work everywhere. Same asymmetry here. The injected runner raises
`FileNotFoundError(2, …, 'docker')` — `docker` not on PATH, the realistic shape
— and teardown reports it, removes what the manifest records anyway, and exits
0. It does not point the operator back at the compose file, because the two
lines below it are about to delete that file.

```text
3/6 stop the engine container: take the engine container down from /tmp/…/state/supervision/container/compose.yaml and remove the 4 file(s) this engine wrote under /tmp/…/state/supervision/container: .env, compose.yaml, ergane-engine.profile, seccomp-ergane.json
    kept: /tmp/…/state-home/ergane (the state root; this step removes nothing outside the engine container's own project directory)
    kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
    could not take the engine container down — `docker compose -f /tmp/…/state/supervision/container/compose.yaml down` could not be run: [Errno 2] No such file or directory: 'docker'
      the files below were removed from what the manifest records anyway; if that container is still running, `docker ps` names it
    removed: /tmp/…/state/supervision/container/.env
    removed: /tmp/…/state/supervision/container/compose.yaml
    removed: /tmp/…/state/supervision/container/ergane-engine.profile
    removed: /tmp/…/state/supervision/container/seccomp-ergane.json
    removed: /tmp/…/state/supervision/container
```

The run reached step 6 and ended, exit 0:

```text
teardown done: pause dispatch, forget repositories, stop the engine container, stop and remove units, clear state (nothing to do), account for git refs (nothing to do)
```

The other half — a daemon that is there and answers non-zero — reads the same
way, and is asserted in
`test_a_daemon_that_answers_nonzero_is_reported_the_same_way`. Compose says most
of what matters across several lines; they are folded onto one, because
teardown's report is one indented line per fact:

```text
    could not take the engine container down — `docker compose -f /tmp/…/state/supervision/container/compose.yaml down` exited 1: Cannot connect to the Docker daemon
```

## 5. The refusal that precedes every step (FR-018)

`removal_targets` is wired, and the guard is handed the project directory before
the loop starts — asserted by making that directory contain the install root and
reading the refusal, because a target the guard never sees bounds nothing
(`test_the_fr018_guard_sees_the_project_directory_before_any_step_acts`):

```text
ergane: refusing to run teardown: step 'stop the engine container' would remove /tmp/…/state/supervision/container, which contains the install root /tmp/…/state/supervision/container/us7 — the installation this process is running from. Teardown would delete itself mid-run and leave a host no report describes; there is no flag for this
```

with `host.events == []`, the schedule present, and `compose.yaml` still on
disk: nothing was paused, forgotten, taken down or removed.
