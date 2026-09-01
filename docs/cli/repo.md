# `ergane repo`

> manage target repositories

Validate a target repository and manage its runtime state. `init` joins a
repository; `repo` looks after the ones already joined.

```
ergane repo onboard              <target-repo> [--json]
ergane repo list
ergane repo rebuild              [<repo-path>...] [--lock-timeout SECONDS]
ergane repo forget               <slug> [--clean-runtime] [--export DIR] [--lock-timeout SECONDS]
ergane repo migrate-runtime-root [--yes]
```

---

## `ergane repo onboard <target-repo>`

Judge a repository's fitness as a target and report a profile. `--json` emits
the machine-readable version.

Read-only. Use it before `init` to find out what a repository is missing.

---

## `ergane repo list`

One line per registry entry with the current status of its committed manifest —
`valid`, `invalid` or `missing`.

```
$ ergane repo list
no repos are registered; run `ergane init` inside a repository to join one
```

**The registry is a cache, and the manifest is the truth.** A `missing` or
`invalid` status is a statement about the repository's own committed
`ergane.yaml`, not about the registry row.

---

## `ergane repo rebuild [<repo-path>...]`

Adopt the repository paths given, prune entries whose repositories are gone, and
leave live entries untouched. Safe to run at any time — the registry is a cache,
so rebuilding it cannot lose anything that is not recoverable from the manifests.

Each path given must carry a committed manifest.

`--lock-timeout` (default 30s) is how long to wait for another writer to release
the registry lock before **refusing**. It does not block forever.

---

## `ergane repo forget <slug>`

Delete the repository's roadmap schedule from the control plane and remove its
registry entry.

| flag | meaning |
| --- | --- |
| `--clean-runtime` | also empty the repository's runtime root, once no epic is running; the directory itself stays, because the repo still ignores it |
| `--export DIR` | **first** write this repository's engine-side records — findings, usage, escalations — into `DIR` as one JSONL file per store plus a markdown digest |
| `--lock-timeout` | seconds to wait for the registry lock (default 30) |

**The repository's own files are left exactly as they are** — the manifest, the
`.gitignore` line and `.ergane/`. Removing those is your git work, deliberately,
because they are committed content and this command does not write to anyone's
history.

**`--export` runs first and is the reason to reach for it.** Findings, usage and
escalations are engine-side; forgetting a repository discards its history unless
it is exported. `DIR` must lie outside the runtime root, for the obvious reason.

---

## `ergane repo migrate-runtime-root`

Move the worker-host runtime root from the legacy `.factory/` name to `.ergane/`.

| flag | meaning |
| --- | --- |
| `--yes` | perform the move; **the default is a dry run** |

Refuses while any epic is running.

## See also

- [`ergane init`](init.md) — join a repository in the first place
- [`ergane uninstall`](uninstall.md) — take the whole installation off the host
