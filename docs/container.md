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

## Preserve the state and supervision mounts

The Ergane state root normally lives at `/home/<operator>/.local/state/ergane`.
Its `supervision` subdirectory holds generated supervision artifacts and frozen
native-worker deployments. Temporal history is a sibling of that subdirectory,
not a file inside it:

- Native managed Temporal: `<state root>/temporal/dev.db`.
- Generated container project: `<state root>/temporal/engine.db`.

The generated compose project mounts both the state root and supervision home,
plus the resolved configuration directory and registered repositories at their
same absolute paths. Keep those declarations intact. The **state-root** mount
preserves `engine.db` across container recreation; mounting only the supervision
subdirectory does not. Check the actual generated database path and volume
coverage when using non-default locations.

The two engine tiers deliberately use different SQLite files. Switching tiers
does not migrate workflow history. Do not point two running Temporal servers at
one file or copy a live SQLite database as an upgrade step. A history migration
requires a separately planned, quiescent backup/restore and recovery check.

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

## Gateway and subscription credentials are different paths

Codex gateway builders use per-attempt gateway keys, not a ChatGPT login. See
[Codex gateway setup](codex-gateway-setup.md); an operator's session provider,
the builder's runner/route, and the independent judge remain separate choices.

A copied subscription credential is a separate writable file, **not an
independent login or refresh-token stream**. Copies can still interfere when
the provider rotates a token, and throwing away a refreshed copy loses the
state needed by the next attempt. Do not use file copying as evidence that
concurrent subscription attempts are safe.

OpenAI's [managed-account automation guidance](https://learn.chatgpt.com/docs/auth/ci-cd-auth)
requires preserving the credentials refreshed by Codex and serialized use of
the credential stream on trusted private infrastructure. It is distinct from
the gateway procedure. Credential ownership, host/container delivery and the
applicable target-policy qualification must be established before enabling a
subscription rung; this container guide does not establish them. Do not mount
your interactive operator's writable Codex home into builders.

## Extending the image for target toolchains

The base image ships the factory's own toolchain (Python, uv, Node.js, Git and
agent CLIs). Check the actual image's pinned CLI versions and supported sandbox
layout; a working host CLI is not proof of the container's tools. Repositories
that need system libraries or languages outside that set
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

Choose and manage the container tier from the host's `ergane install` flow.
Do not use `ergane worker install` or native `worker deploy` inside the container;
those commands require host systemd-user supervision and a native checkout.
Container-safe configuration/verification paths are separate from installing
host units. Operate the generated compose project, not a newly invented compose
file or an unversioned worker started alongside it.

## The reference compose is a reference

`container/compose.reference.yaml` is the shape the generator emits, checked into
the repository so the drift tests can prove no required key is removed.  Your
operational project is produced by `ergane install` (spec 104), which substitutes
the actual state root, supervision home, registered repos, and per-repo
same-path mounts from the interview answers.

## Upgrading the engine

The intended `ergane engine upgrade` sequence validates the generated project's
ownership, retargets its persisted service image and version to the CLI-matched
published image, then stops the engine, starts that image with the version in
the Compose child's environment, verifies and retains a rollback image. It
refuses open epics unless forced, and refuses changed, unclaimed, missing or
unsupported project artifacts always; force does not bypass ownership.

**Do not use automated container upgrade until its image lifecycle is
qualified.** The repaired boundaries — the persisted project retargeting, the
requested version reaching the Compose child, the pre-stop identity ordering
and the cleanup selection — are covered by committed captured-runner
regressions, and those captures are synthetic: no Docker daemon ran. A real
drained-image upgrade and rollback remains operator qualification before
release. The native versioned-worker deployment path is separate and is not
affected by these specific findings.

Before a container upgrade, preserve the resolved configuration and persona
registry, workflow history, verification/usage stores and required attempt
evidence. Record the actual current image reference/digest and intended target.
Do not use `--force` or broad image pruning to get past an unexplained failure.
See the [engine reference](cli/engine.md) for the command's current limits;
an image retained on disk alone is not a tested rollback procedure.
