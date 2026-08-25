# 104-US3 — writing, remembering and removing the project (seam capture)

**This is a seam capture, not a session at a terminal.** A scratch host under
`/tmp/us3-capture/root` was pointed at by `HOME`, `ERGANE_STATE_HOME` and
`XDG_CONFIG_HOME`; `container_project.resolve_project` rendered a project from an
injected `ControlPlaneConfig` and a one-repo fixture `repos.json`; then
`container_manifest` wrote it, wrote it again, refused an edited file, and
removed what it could still prove was its own. Those are the closed seams — a
relocated state home, an injected config, a fixture registry. **No supervision
home was touched, no Docker daemon contacted, no container started and
`apparmor_parser` never invoked** (trap 11). The agent sandbox binds no Docker
socket, so a plausible-looking real transcript would be indistinguishable from a
fabricated one; the real runs are the operator's, in `plan.md`'s verification
list.

## 1. The first write, and what the manifest recorded

`write_project(project)` takes the four `GeneratedFile`s of `project_files` — R5's
compose, `.env` and the two confinement-artifact copies — and records a digest for
each.

```
wrote 4 file(s) to /tmp/us3-capture/root/state/ergane/supervision/container
  wrote: compose.yaml
  wrote: .env
  wrote: seccomp-ergane.json
  wrote: ergane-engine.profile
```

The directory, with each file's mode and the digest `installed.json` recorded for
it:

```
600  .env                   19813d16fd0b3ac27ac0d3b8f2784f800c075c8e77a224cd0fe192fa1c385419
644  compose.yaml           300ade39363fda601d7174cfa4410f3267522d9378279ea571939326de64db18
644  ergane-engine.profile  0b153583abca80d0b1cc9b767a50b7f27d004f3aaba55658ffb464e269426890
644  installed.json         — (the manifest itself)
644  seccomp-ergane.json    6c5bf38caf59888f2e86ebd5199dd9264b3943044d07e0b3ae6812535ab9bc8a
```

`.env` keeps the `0600` the renderer gave it: no secret is written there, but a
file by that name attracts them. The manifest's own mode is pinned rather than
left to the umask, so the project does not read differently on two hosts.

## 2. The second write is a no-op, on the bytes

Not "the report says nothing changed" — every file in the directory, the manifest
included, compared byte-for-byte across the second call:

```
engine container project at /tmp/us3-capture/root/state/ergane/supervision/container is already current
  unchanged: compose.yaml
  unchanged: .env
  unchanged: seccomp-ergane.json
  unchanged: ergane-engine.profile

.env                   bytes identical -> True
compose.yaml           bytes identical -> True
ergane-engine.profile  bytes identical -> True
installed.json         bytes identical -> True
seccomp-ergane.json    bytes identical -> True
(file set)             identical      -> True
```

Two halves make that true: the renderer is a function of the project data alone
(US2), and the manifest is written `sort_keys=True, indent=2`. A converged
install stops touching the directory at all — the writer skips files whose digest
already matches rather than rewriting identical bytes.

## 3. A hand edit is refused by name, never clobbered

The operator edits `compose.yaml` — the realistic edit, republishing the port
because the native tier holds 7233 — and `ergane install` runs again:

```
engine container project at /tmp/us3-capture/root/state/ergane/supervision/container: wrote nothing, 1 file(s) left as the operator left them
  unchanged: .env
  unchanged: seccomp-ergane.json
  unchanged: ergane-engine.profile
  refused to overwrite (changed since ergane wrote it): /tmp/us3-capture/root/state/ergane/supervision/container/compose.yaml
  the engine will run what is on disk; move the file aside to have `ergane install` generate it again
```

The bytes on disk afterwards are the operator's:

```
# hand-tuned: published on 7333, the native tier holds 7233
services: {}
```

The rule is `_is_someone_elses` (`factory/supervision/units.py:962`), imported
rather than copied: the file is refused because its **digest** is not the one
recorded, not because of anything about its name. A filename allow-list cannot
tell this case from the first write and would have overwritten it —
`test_the_refusal_is_by_digest_and_not_by_filename` is that difference, and it
puts a stranger's file at a name the writer *would* write before any manifest
exists.

The refused file also drops out of the record, which is what makes teardown leave
it alone:

```
manifest claims: ['.env', 'ergane-engine.profile', 'seccomp-ergane.json']
```

## 4. Removal takes ours and nothing else

With that edit still in place and one file the engine never wrote
(`operator-notes.md`), `remove_project(layout)`:

```
engine container project at /tmp/us3-capture/root/state/ergane/supervision/container:
  removed: .env
  removed: ergane-engine.profile
  removed: seccomp-ergane.json
  kept (not written by ergane): /tmp/us3-capture/root/state/ergane/supervision/container/compose.yaml
  kept (not written by ergane): /tmp/us3-capture/root/state/ergane/supervision/container/operator-notes.md
  left the project directory: it still holds files ergane did not write

left in the directory:
  compose.yaml
  operator-notes.md

installed_project(layout) -> None
```

Both survivors are named with a path and a reason, because "kept 2 file(s)" is
not something an operator can act on. `compose.yaml` reads as *unclaimed* rather
than *changed* here for an honest reason: step 3's refusal already dropped it
from the manifest, so removal meets a file it cannot prove it wrote. Where no
install ran between the edit and the teardown the manifest still carries the old
digest and the reason is `changed since ergane wrote it` —
`test_remove_project_removes_only_files_whose_digest_still_matches` covers that
path. Either way the file stays.

Removal reads the manifest and nothing else — no render, no config, no daemon
(trap 13). `test_removal_reads_the_manifest_alone_and_never_re_renders` deletes
`config.toml` and `repos.json` first, so `resolve_project` could not have run,
and the teardown still knows what to remove.

## 5. A clean project is removed whole, and state is not

Same host, nothing in the directory but the engine's own files:

```
engine container project at /tmp/us3-capture/root/state/ergane/supervision/container:
  removed: .env
  removed: compose.yaml
  removed: ergane-engine.profile
  removed: seccomp-ergane.json
  removed the project directory
project directory exists -> False
state root still there   -> True
config.toml still there  -> True
installed_project(layout) -> None
```

`installed_project` answering `None` is the record R1 puts on disk instead of in
`config.toml`: a host with a project runs the container tier, a host without one
does not, and US5, US6 and US7 ask exactly this question.

## The committed tests

```
$ uv run pytest tests/test_container_manifest.py
collected 22 items

tests/test_container_manifest.py ......................                  [100%]

============================== 22 passed in 0.55s ==============================
```
