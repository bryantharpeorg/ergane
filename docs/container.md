# Ergane in a container

The container tier is the *contained/removable/portable* tier: the same engine
that runs natively under systemd user units, packaged so it can be started and
discarded without touching the host's service state.  On Linux, the native tier
remains the recommended default; choose the container when you want full
encapsulation, or when the host has no usable systemd user session.

## Same-path mounts are the invariant

Every bind mount in the generated compose project must use the **same absolute
path on the host and in the container**.  This is not a convenience: git stores
absolute paths in `.git/worktrees/<name>/gitdir` and in each worktree's `.git`
file.  When those paths are identical on both sides, a worktree created on the
host can receive commits from inside `bwrap` inside the container and read as a
clean checkout on the host immediately afterwards.

The supervisor checks this before starting any child (FR-009,
`factory/supervision/container_supervisor.py:_check_same_path_registry`).  If a
registered repo's recorded path is not a directory, the container refuses and
names both remedies, verbatim (`SAME_PATH_REMEDIES` in that module, quoted here
and held to it by `tests/test_container_supervisor.py`):

```text
remedies: run `ergane init <repo path>` on the host, which regenerates the
engine container's mount list with that repo at its own path and reconciles
the engine; or, if the recorded path is stale rather than merely unmounted,
rebuild the registry with `ergane repo rebuild <repo path> ...`
```

`ergane init` is named first because it is the verb that fixes the case that
actually happens: a repo joined after the engine came up is registered but not
yet mounted, and `ergane init <repo path>` regenerates the project's mount list
and reconciles the engine in one command (spec 104, US6).  Rebuild remains the
remedy for the other case — a recorded path that is stale rather than unmounted,
where no mount would help because the registry is what is wrong.

## Mount the supervision home, not just the state root

The state root (`~/.local/state/ergane` by default) holds the repo registry and
durable engine state.  The supervision home (`~/.local/state/ergane/supervision`)
holds the generated systemd units and the managed Temporal dev-server's SQLite
database.  The Temporal database lives **one directory above** the supervision
subdirectory, so a `compose down && up` that mounts only the state root silently
discards all workflow history.  The reference compose mounts both explicitly.

The engine container does not share that database.  It writes its own history to
`<state root>/temporal/engine.db`, beside the native tier's `dev.db` and never
into it: two Temporal servers on one SQLite file is the same-host corruption
hazard the same-path research exists to prevent.  The **state-root** mount carries
`engine.db` across a `compose down && compose up`; the supervision-home mount does
not, that database being a sibling of the supervision home rather than a child.
One intended consequence: a host switching from the native tier starts with
**empty workflow history** — migrating is an operator move, stopping both tiers
and copying the file by hand.

## Confinement artifacts

Two files define the container's sandbox contract:

- `container/seccomp-ergane.json` — a vendored copy of the moby default seccomp
  profile (v28.3.3) with the `clone3` ERRNO rule removed and an unconditional
  allow added for `unshare`, `clone`, `clone3`, `mount`, `umount2`,
  `pivot_root`, `setns`.
- `container/ergane-engine.profile` — a moby `docker-default` AppArmor profile
  plus `abi <abi/4.0>` and explicit `userns`, `mount`, and `pivot_root` allows,
  retaining every `/proc` and `/sys` write deny that docker-default carries.

Both files carry a comment naming their upstream base and version.  They are the
reference configuration; hosts where loading a custom AppArmor profile is
unacceptable can fall back to **config F** (`apparmor=unconfined`) documented in
`docs/container-onramp-research-findings.md`, which depends on a host-loaded
`bwrap` stub that the installer must place.

## Subscription credential trade-off

Subscription-routed personas (`factory/workgraph/adapter.py:767`) run the agent
runner against the operator's own credential.  The factory copies that credential
into each per-node HOME (`factory/workgraph/adapter.py:803`) so concurrent nodes
do not share a writable credential file.  The operator's stored credential is
never written to by an agent.  If the provider rotates refresh tokens on use, the
copy still isolates concurrent nodes from invalidating one another, but the
operator's own host login may be invalidated when the first node refreshes — a
trade-off documented here and in the code.

## Extending the image for target toolchains

The base image ships the factory's own toolchain (Python, uv, node, git, the
agent runner).  Repos that need system libraries or languages outside that set
can extend the image with:

```dockerfile
FROM ghcr.io/bryantharpeorg/ergane:X.Y.Z
RUN apt-get update && apt-get install -y libpq-dev
```

The tag `X.Y.Z` is always equal to the CLI version; the startup handshake
refuses to run a mismatched engine and prints both remedies — the exact
`docker pull ghcr.io/bryantharpeorg/ergane:<cli>` command to run, and
`ergane engine upgrade` — plus the absolute path of the stale identity record
to remove if the engine is gone.

## Verbs the container does not support

The container tier runs the engine; it does **not** run `ergane install` or
`ergane worker install` inside itself.  Those verbs install systemd user units on
the host.  The container's operational project is generated by `ergane install`
in spec 104 and is started with `docker compose up`.

## The reference compose is a reference

`container/compose.reference.yaml` is the shape the generator emits, checked into
the repository so the drift tests can prove no required key is removed.  Your
operational project is produced by `ergane install` (spec 104), which substitutes
the actual state root, supervision home, registered repos, and per-repo
same-path mounts from the interview answers.

## Upgrading the engine

`ergane engine upgrade` moves the running container to the image that matches
this CLI version.  It refuses while any epic is in flight, naming the open
epic and what stopping the engine now would cost; pass `--force` only when
you are willing to strand that work.  Once the floor is drained, the verb stops
the running engine, starts the new pinned image, verifies through it with the
same `ergane install --verify` battery, and removes local images that are
older than the immediately previous version.  It keeps exactly two versions:
the one it just started and the one it replaced, so a failed upgrade has a
known rollback target.
