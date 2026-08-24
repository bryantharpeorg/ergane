# Research findings: the containerized developer onramp

**Answers**: `docs/container-onramp-research-brief.md` (written 2026-08-23 against 0.3.0).
**Produced**: 2026-08-23, by an operator research session with access to the brief's
target host. Method: five parallel research agents over primary web sources, plus —
because the session ran *on the floor host* — live experiments that settle Q1 and the
Linux half of Q3 empirically rather than from citations.

**Experimental substrate** (matters for scope): Ubuntu 24.04.4 LTS, kernel
6.17.0-1018-nvidia, **aarch64** (the floor host is arm64 — itself a finding, see Q4),
Docker 29.2.1 rootful, overlayfs, AppArmor + seccomp active,
`kernel.apparmor_restrict_unprivileged_userns = 1`, bubblewrap 0.9.0. Runnable
artifacts (test image Dockerfile, probe matrix, seccomp profile, candidate AppArmor
profile, verification script) are embedded in the appendix of this document.

---

## 0. Executive answer

The §5b design survives, with three corrections and one reframe.

1. **Q1 is settled, by experiment, in a better place than the brief feared.** bwrap
   runs inside Docker on this host with **no `--privileged`, no added capabilities,
   and the default seccomp replaced by a ~10-line-delta custom profile**. The brief's
   assumed `apparmor=unconfined + seccomp=unconfined` pair is not just bad optics —
   as tested it **does not even work** (details in §1). The working recipe is
   non-root user + narrow seccomp + an AppArmor arrangement with two variants: one
   that works today with zero host setup beyond what the native path already needed,
   and a strictly better one (`ergane-engine` profile, **verified end to end**)
   that needs a single `apparmor_parser` load at install time and keeps full
   AppArmor mediation — the sandbox child provably stays confined under it.
2. **Reframe (Q6a): the container is the *encapsulation* tier, not the onramp.** The
   prior-art evidence is one-directional: every tool that optimized time-to-first-
   success went native-single-process (Temporal built `start-dev` specifically to
   escape compose; TrueForge's local tier is container-less by design), and every
   host-CLI-fronting-containers product pays a permanent "container is not ready:
   unhealthy" tax at its front door (four years of Supabase's tracker). Ergane's
   native Linux closure is Temporal-shaped, not LocalStack-shaped — there is no
   dependency hell for a container to solve. So: **keep the native systemd tier as
   the Linux default; ship the container as the contained/removable/portable tier**,
   framed by capability ("what do you want contained?"), never as a symmetric menu.
   Ease then comes from `ergane install` doing more (personas, scaffold, smoke —
   §5–§7), exactly as the brief's Q6a suspected. This reorders the five stories but
   invalidates none of them.
3. **The host CLI reading container SQLite is safe on Linux and only on Linux** —
   proven here by concurrent-writer experiment, and condemned on macOS/Windows by
   documented VirtioFS/gRPC-FUSE evidence. The design consequence is a clean split:
   on the Linux container tier, keep the bind-mounted state root and same-path
   mounts (the full sandwich — container → bwrap → git worktree at its host path →
   host visibility — is verified end to end below); a future macOS tier must read
   state through the engine, not the filesystem, and should be designed as such from
   the start rather than retrofitted.
4. **Version contract: derive, auto-pull, refuse to run mismatched** — the Dagger
   model, which is the only alignment scheme in the survey that generates no support
   load. Image tag is a pure function of CLI version; details and registry choice in
   §4.

---

## 1. Q1 — bwrap inside Docker, settled empirically

### What actually blocks it (each blocker isolated by experiment)

The brief guessed "AppArmor plus the userns sysctl." The measured reality is five
distinct blockers, several of which the assumed fix does not address:

| # | Blocker | Evidence |
| --- | --- | --- |
| 1 | **Docker's default seccomp profile** gates every namespace-related syscall on `CAP_SYS_ADMIN`: `unshare`, `mount`, `pivot_root`, `setns`, `umount2` are absent for unprivileged containers, `clone` is allowed only with all `CLONE_NEW*` bits masked (`0x7E020000`), `clone3` is explicitly `ERRNO` | Read from moby `profiles/seccomp/default.json` (v28.3.3); confirmed live — default config fails `unshare -U` with EPERM |
| 2 | **Container root is the wrong user for bwrap.** As uid 0, bwrap skips its userns path entirely and issues a bare `clone(CLONE_NEWNS)` (strace-verified), which requires `CAP_SYS_ADMIN` the container doesn't have. The brief's assumed both-unconfined recipe fails *because of this* — unconfined-ness never enters into it | strace: `clone(child_stack=NULL, flags=CLONE_NEWNS\|SIGCHLD) = -1 EPERM` |
| 3 | **`docker-default` AppArmor permits userns creation but denies bwrap's mounts.** The mechanism is subtle and documented: the template has *never* contained a `userns` rule — it is pinned at AppArmor ABI 3.0, which predates userns mediation, and per the AppArmor wiki such profiles are simply not subject to the userns restriction ("the net effect is these profiles can be used to by-pass user namespace controls"). So confined-by-docker-default processes create userns *with capabilities retained* — and then hit the template's explicit `deny mount,` at `Failed to make / slave` | Matrix configs 2/B/C/E, mechanism from AppArmor wiki + moby/profiles source (research agent) |
| 4 | **`apparmor=unconfined` makes Ubuntu *worse*, not better.** With the profile removed, `apparmor_restrict_unprivileged_userns=1` shunts the unconfined process into the capability-stripping `unprivileged_userns` transition profile: the namespace is created but `uid_map` writes EPERM | Matrix config 4: `unshare: write failed /proc/self/uid_map: Operation not permitted` |
| 5 | **bwrap must not be container PID 1.** Invoked directly as the entrypoint it fails `setting up uid map: Permission denied`; as a child of any init (tini via `init: true`, or the engine supervisor) it works. A preflight that execs bwrap as the entrypoint would report a false negative | Isolated by `--init` A/B test |

### The two working configurations

**Config F — works today, no root on the host beyond what native already needed:**

```yaml
# compose fragment, verified (as docker run flags) on this host
init: true                      # blocker 5
user: "1000:1000"               # blocker 2; also fixes bind-mount ownership (§3)
cap_drop: [ALL]                 # verified compatible
security_opt:
  - no-new-privileges:true      # verified compatible — does not break attachment
  - seccomp:./seccomp-ergane.json   # blocker 1: moby default + 7 syscalls (appendix)
  - apparmor:unconfined         # see mechanism below
```

Under this config the full Ergane-shaped sandbox — `--ro-bind /usr`, bin/lib/sbin
symlinks, `--proc`, `--dev`, tmpfs `/tmp`, worktree bound writable at its own
absolute path, `--clearenv` — runs, executes python, writes to the worktree, and has
network egress (TCP to an external host verified from inside the sandbox).

**The mechanism, and its hidden host dependency.** `apparmor=unconfined` works here
*only because* on exec of `/usr/bin/bwrap` the kernel attaches the host-loaded
`bwrap` AppArmor stub profile (`flags=(unconfined) { userns, }`) — verified by
reading the sandbox child's label: `bwrap (unconfined)`. That grants userns creation
with capabilities retained, sidestepping blocker 4. Two consequences:

- **That stub is not stock Ubuntu 24.04.** The `apparmor` package ships ~90 such
  stubs (`crun`, `podman`, `linux-sandbox`, `flatpak`…) but **not** `bwrap`; the
  bubblewrap .deb doesn't ship it either. The one on this host is unowned by any
  package, root-created 2026-07-16 — someone hand-installed it, presumably during
  Ergane's original sandbox bring-up. This means the **native path has the same
  undocumented host dependency**, and the brief's appendix line "Ubuntu 24.04's
  AppArmor profile permits…" describes a local artifact, not a distro default.
  `ergane install` should own placing this file (one sudo write + `apparmor_parser
  -r`), and the story-1 preflight should verify bwrap *executes*, in both tiers.
- The attachment happens against the *container's* `/usr/bin/bwrap` (path matching
  is namespace-relative), so the image must carry bwrap at exactly that path —
  which it would anyway, given the launcher's deliberate absolute-path pin.

**Config G — the recommended target — VERIFIED 2026-08-23 ~9:05 PM CT:**

Same as F but `apparmor:ergane-engine` — a custom profile built from moby's
docker-default template with three deltas: `userns,` allowed, `deny mount,` replaced
with `mount, umount, pivot_root` allows, and peer names updated (full text in the
appendix). Every deny rule docker-default carries (`/proc` write masks, `/sys`
masks, ptrace scoping) is retained. The operator loaded the profile
(`apparmor_parser -r`) and the full suite passed: userns creation, minimal and
full-mount-set bwrap, **sandbox child labeled `ergane-engine (enforce)`** (no
transition out — mediation intact end to end), plus the heavyweight checks re-run
under G: host-created git worktree committed to from inside the sandbox, network
egress from the sandbox, and concurrent host+container SQLite (4,000 commits,
integrity ok). G does **not** depend on the hand-installed `bwrap` stub that F
leans on — the container's own profile carries the grant — so it is also the
config predicted to work unchanged on stock Ubuntu hosts.

**Why G over F**: with G the compose file reads as what it is — a *named, narrower
sandbox contract* (`apparmor:ergane-engine`, `seccomp:./seccomp-ergane.json`,
`cap_drop: ALL`, `no-new-privileges`) rather than any `unconfined` token; and the
engine keeps AppArmor file/proc/sys mediation that F gives up. The trust pitch in
§2 of the brief is then literally true and visible in the artifact a developer
inspects.

### What this session could not test

- x86_64: all experiments ran on arm64. No mechanism involved is arch-specific
  (the seccomp deltas carry no arch conditions beyond moby's own), but a one-run
  confirmation on an amd64 box is cheap and worth doing.
- A stock Ubuntu 24.04 host (no hand-installed bwrap stub): config F is predicted
  to fail there until the installer places the stub; G does not depend on it.
- Non-Ubuntu hosts: on distros without the userns restriction (Debian 12 default,
  Fedora — which runs SELinux, not AppArmor), blockers 3/4 vanish and the narrow
  seccomp alone should suffice; untested here.

### The documentary picture (research agent, primary sources)

The web-research pass confirms and sharpens the empirical one:

- **The seccomp gate is deliberate and is not going away.** Docker's default
  profile has *never* permitted unprivileged userns creation and still does not
  as of 29.7.2: `clone` is argument-filtered to zero `CLONE_NEW*` bits,
  `clone3` returns ENOSYS to force the filterable fallback, and
  `unshare`/`mount`/`pivot_root` live only behind `CAP_SYS_ADMIN`
  (`pivot_root` appears *nowhere*, denied even with the cap). The relaxation
  request has been open since 2021 (moby#42441) with two unmerged 2025 PRs
  against moby/profiles — so a custom profile is the designed-in answer, not a
  workaround for a bug about to be fixed. A **maintained drop-in alternative to
  hand-carrying the delta exists**: containers/common `seccomp.json` (the
  podman/buildah/CRI-O default) unconditionally allows `clone`/`clone3`/
  `unshare`/`mount`/`pivot_root` and tracks new syscalls upstream — shipping
  that file (vendored, version-recorded) trades "maintain a diff against moby"
  for "adopt the containers-project default," and the community documents using
  it under Docker for exactly this purpose.
- **The masked-/proc blocker exists in the wild but did not bite here.** The
  kernel refuses a fresh procfs mount in a user namespace unless the existing
  proc is "fully visible" (bubblewrap#284 documents `Can't mount proc:
  Operation not permitted` inside Docker). On this kernel (6.17) the mount
  succeeded, and a follow-up probe showed bwrap mounts a genuinely fresh procfs
  and then **re-masks the same 13 paths Docker had masked** — the sandbox does
  not unmask what the container masked. Treat this as kernel-dependent: the
  story-1 preflight must exercise the full mount set *including `--proc`*, and
  if a target kernel refuses it, the documented knobs are, in order,
  `--security-opt systempaths=unconfined` (coarse: unmasks the container's own
  /proc, partially re-covered by the AppArmor denies and by bwrap's re-masking)
  or the degraded bind-`/proc` mode Anthropic's sandbox-runtime ships for
  exactly this case.
- **Profile authorship details that matter for config G**: the AppArmor ABI
  declaration decides whether userns mediation applies at all — under
  `abi <abi/4.0>` the `userns,` rule is required and enforced; under abi/3.0 it
  is moot (ABI bypass). The candidate profile in the appendix is authored
  abi/4.0 + `userns,`, the future-proof choice. Incus's generated per-instance
  profile is the production model for the mount rules and shows the hardening
  headroom: scoped `mount fstype=(proc,tmpfs,devpts,...)` rules instead of the
  bare `mount,` this candidate starts with.
- **Nobody comparable runs narrow-profile nested bwrap — they either give up
  or go privileged.** Bazel documents that linux-sandbox needs `--privileged`
  in Docker and silently degrades to a no-isolation wrapper; flatpak's own CI
  action instructs `options: --privileged`; the devcontainer docker-in-docker
  feature declares `privileged: true`; Nix-in-Docker defaults to
  `sandbox = false`. Anthropic's sandbox-runtime treats bwrap-inside-Docker as
  an explicitly degraded mode ("considerably weakens security"). The narrow
  configuration verified above is therefore *ahead of* the prior art, not
  behind it — worth knowing both as a trust-pitch fact and as a warning that
  few others have walked this path.
- **Podman rootless is materially better on three of the four blockers**
  (permissive-by-default seccomp, per-path `unmask=`, no AppArmor profile
  applied rootless) — at the cost of leaving the operator's rootful Docker 29
  deployment, compose-compatibility caveats, and different uid-mapping
  semantics for the bound worktrees. Right answer to keep in the back pocket,
  wrong first target.

### The alternative shape: one container per agent node

The strongest argument *for* it is that everyone comparable landed there
(OpenHands: the container is the sandbox; E2B: Firecracker microVMs at
~125–200 ms startup; container create/start is sub-second against multi-minute
attempts). The strongest argument *against* it, and the reason to reject it
here: the engine would then have to command a container runtime from inside its
own container, and every documented path for that is worse than the narrow
relaxations — mounting `docker.sock` into the engine is host-root-equivalent
(sandbox-runtime's README says so in as many words), DinD requires
`--privileged`, and sysbox requires installing a custom runtime on the host,
forfeiting "docker run and go." Bwrap-in-container concentrates its loosening
at the agent layer, where a profile still confines; sandbox-as-container
relocates the trust problem to the orchestration layer, where the known
solutions are all-or-nothing. It also turns Ergane's one state-root bind into
per-node mount choreography. Verdict: keep bwrap as the agent boundary inside
the engine container (constraint honored, and now evidenced rather than
assumed); revisit one-container-per-node only if config G fails verification on
stock hosts.

---

## 2. Q2 + Q6a — prior art on the shape, and whether the container is the ease lever

The research agent's full survey (TrueForge, Supabase CLI, LocalStack, Temporal,
Dagger, Tilt, Colima/Lima, devcontainer CLI, Testcontainers, Stripe CLI; sources
dated, accessed 2026-08-23) reduces to three transferable lessons and a verdict.

**Lesson 1 — bundle or derive, never coordinate.** The two version-alignment models
that generate no support load are Temporal's (engine embedded in the CLI binary —
skew impossible) and Dagger's (`registry.dagger.io/engine:v<CLI version>` — tag is a
pure function of CLI version, auto-pulled). Supabase's maintainers *refused* user-
pinnable engine versions explicitly to avoid owning a CLI×image compatibility matrix
(supabase/cli#2435, closed not-planned). The failure residue of "derive" is stale
engines accumulating across upgrades (Dagger #8561: ~600 GB of volumes; Supabase
stale-container states #3798/#4756) — **an upgrade path must also be a cleanup
path**.

**Lesson 2 — the container is a team/portability/encapsulation lever, not an onramp
lever.** Temporal's own history is the decisive datapoint, because Temporal *is*
Ergane's orchestrator: they built Temporalite → `temporal server start-dev`
("Docker can represent additional overhead and indirection, which slows you down",
Temporal blog 2023-03-30) and archived their compose repo (2026-01-05). TrueForge —
the brief's Q2 anchor — draws its local/team line at *multi-user state and auth*,
not at packaging; "the agent features are identical in both modes." The only
surveyed project that went container-only, LocalStack, did so to solve a huge
fast-churning Python dependency closure — a problem Ergane's static-binary +
SQLite + git closure does not have. Meanwhile the permanent front-door tax of
CLI-fronting-containers is documented across four years of Supabase issues: the
health gate becomes the product's front door, and every image's startup race
becomes the CLI's bug.

**Lesson 3 — engine state stays behind the engine's API; only user-owned files
cross the mount boundary.** Unanimous across the survey: named volumes (or
in-engine storage) for engine state, bind mounts for user config and source, and
no surveyed tool has its host CLI open the engine's database files across the
container boundary — every one reads through a published port or API. Ergane's
planned bind-mounted-SQLite read path is the single element of §5b with direct
prior-art evidence against it — **but only off Linux** (see §3; on Linux the
same-kernel bind mount is exactly a shared local filesystem, and this session
verified it under concurrent load).

**Verdict on the two-tier question (Q6a): native + container, native as the Linux
default.** Present it capability-framed, minikube/Ollama-style — one recommended
default per context plus a one-sentence exception rule, e.g. *"On Linux, `ergane
install` runs the engine natively under systemd user units. Choose `--engine
container` if you want the engine fully contained and removable, or your Linux has
no systemd user session."* Never a symmetric menu; the axis in user-facing language
is what-you-want-contained, not native-vs-container. The honest cost of two tiers
is a second test matrix; prior art mitigates it by absolute feature parity (only
the supervision backend differs) and by *generating* the compose project from the
same interview and version authority the native tier uses — which is precisely
§5b's shape. Note the systemd-refusal precedent already in the code (managed
Temporal refused without a systemd user session) — the container tier is also the
honest answer for systemd-less Linux.

---

## 3. Q3 — durability and host-visible state

### Linux: proven, with the exact shape that makes it safe

Experiment on this host: one writer inside the container (uid 1000), one writer on
the host, same WAL-mode SQLite file over a bind mount, 3,000 interleaved committed
inserts each. Result: **6,000/6,000 rows, zero `SQLITE_BUSY`, `PRAGMA
integrity_check` ok, WAL intact**, and every file the container created is owned by
the host user. Mechanically this is expected — a Linux bind mount is the same
kernel, same filesystem, same inodes; POSIX advisory locks and the mmap'd `-shm`
file behave as on any local disk; SQLite's "all processes on the same machine"
WAL requirement is satisfied because a container is not another machine. But
"expected" is now "measured."

The end-to-end sandwich was also verified: a git worktree created **on the host**,
bind-mounted **at its identical absolute path**, received a commit from git running
**inside bwrap inside the container**, immediately visible to host git with a clean
status. Same-path mounting is the load-bearing trick — git records absolute paths
in `.git/worktrees/<name>/gitdir` and each worktree's `.git` file (brief appendix),
and identical paths make those records resolve on both sides. This should be a
stated invariant of the compose generator: **every bind mount's container path
equals its host path** — repos, worktrees, state root, supervision home, config.

Three Linux-tier rules fall out:

1. **Run the engine as the host user** (`user: "${UID}:${GID}"` baked in by the
   generator at install time). This simultaneously satisfies bwrap (blocker 2, §1)
   and makes every artifact host-owned. The image must tolerate an arbitrary
   non-root uid with **no passwd entry**: the entrypoint sets `HOME` explicitly
   into the mounted state tree (matching the existing per-node-HOME practice),
   writable dirs come from the mounts, nothing expects `/root`. Do not enable
   dockerd `userns-remap` — it lands state files owned by subordinate UIDs on the
   host, the exact opposite of the goal. (If podman ever enters scope,
   `--userns=keep-id` is the cleaner equivalent.)
2. **Mount the supervision home, not just the state root.** The brief's appendix
   trap stands: the managed Temporal server's SQLite history lives one directory
   above the supervision subdirectory. A recreate that mounts only the state root
   silently discards all workflow history. The generator should mount the common
   parent (or both paths explicitly) and `install --verify` should assert that the
   Temporal history file's host path survives a `compose down && up` round trip.
3. **The state root stays a bind mount, not a named volume** — deliberately against
   the prior-art default (Lesson 3, §2), and justified by what the survey can't
   see: twelve CLI modules read those SQLite files directly, the operator's
   "durable back to disk" requirement is literal, and on Linux the shared-file
   pattern is now measured-safe. Named volumes would break the native↔container
   parity of paths and put state behind `docker volume` plumbing the uninstall
   story would then have to own.

The documentary evidence agrees with the measurement, and adds two facts worth
keeping: SQLite's wal-index deliberately lives in an ordinary mmapped file *next
to the database* precisely so that processes with different root directories
(chroot — and by extension containers) coordinate through the same inode
(sqlite.org/wal.html); and the one real same-host corruption report in the wild
(SQLite forum, May 2026) was **bwrap's overlay feature** giving sandboxes
divergent copy-on-write views of the files — a *different-inode* defect, not a
namespace one. The trap to state as an invariant: **the state directory crosses
boundaries only as a plain bind of the same directory — `.db`, `-wal` and `-shm`
together — never an overlay, never a copy, never a sync, never a single-file
mount.** Host-side read-only opens use `mode=ro` (still lock-coordinated); never
`immutable=1` or `nolock=1` against a live engine — those skip locking entirely
and are documented to return corrupt results under a writer.

### macOS / Windows: shared-file mode is known-broken; design the other path now

The research verdict is unambiguous. On Docker Desktop the container runs in a
VM; a bind mount crosses that boundary via VirtioFS or gRPC-FUSE, and a host
macOS process and a guest Linux process are — in SQLite's own terms — *different
host computers*: no shared kernel page cache, so the two mmaps of the `-shm`
wal-index have no coherency protocol at all, which is precisely the condition
wal.html names as corrupting. The empirical record matches the structure:
VirtioFS corruption under heavy I/O (docker/for-mac#6690, 2023, still open); an
open bug where **multiple threads acquire the same exclusive `flock()`
simultaneously over VirtioFS** (#7004, 2023); corruption under both file-sharing
backends as late as DD 4.36 (#7494, Nov 2024); and a July 2026 report of a
SQLite state DB corrupting in exactly the Ergane shape (Linux container writer,
macOS host). Docker's newer Synchronized File Shares is *worse* for this — a
Mutagen-based bidirectional sync of copies, i.e. two eventually-consistent
copies of a `.db`/`-wal`/`-shm` set. Windows/WSL2 has the same structure
(structural confidence high, direct SQLite evidence thin).

Verdict for the design: **macOS support, when it comes, is "engine-mediated
only"** — state in a named volume, the CLI reading through the engine (a small
read API on the worker, or a containerized-CLI/`docker exec` fallback, or
`VACUUM INTO` snapshot export for offline reads). Ship it as a deliberate mode,
not a degraded copy of the Linux tier, and reword the "operates as if native"
promise there honestly.

### The read-API seam

sqlite.org's own guidance for data separated from the application by a network
boundary is a proxy in front of a single WAL-mode writer — and the Docker
Desktop VM boundary *is* a network for this purpose. Every surveyed same-shape
tool (Supabase, Dagger) reads engine state exclusively over published ports.
For Ergane this does **not** mean building the API now: on Linux the direct-file
path is measured-safe and twelve modules keep working unchanged. It means the
macOS tier's read API, when built, is also the eventual multi-host answer — a
clean seam to leave in the design rather than a retrofit.

---

## 4. Q4 — the version contract

Research verdict (Dagger, DDEV, LocalStack, Testcontainers, k3d, Watchtower
corpus, Datasette's release workflow — full survey in the agent report), plus one
empirical fact from this host that upgrades a "should" to a "must."

**Policy: derive + refuse-with-instructions.** The CLI pins
`ghcr.io/<org>/ergane:X.Y.Z` equal to its own version — the DDEV/Dagger model,
the only one in the survey that generates no correctness complaints (LocalStack
floated on `latest` for years, accumulated a tracker full of silent-drift issues,
and rebuilt its whole tagging scheme in 2026 to escape). On the startup
handshake, a version mismatch **refuses with the exact remedy command printed**.
Never warn-and-continue for a schema-owning engine; never auto-upgrade a stateful
engine under the user — the Watchtower corpus is the documented anti-pattern, and
Ergane's own memory ("worker restart wedges the epic") makes drain-before-replace
non-negotiable. Upgrade is an explicit verb: check no attempts in flight (or
wait/`--force`), stop the worker gracefully, stop the engine, start the new
pinned version, health-probe — and keep the previous image locally for one
release as rollback (Dagger's wipe-on-upgrade drew immediate user anger,
dagger#8195). This contract is *stronger* than what the native tier has today:
nothing currently stops a stale native worker, while a derived image tag
mechanically cannot drift from the CLI that pulled it.

**Pinning and multi-arch.** Immutable `X.Y.Z` tags, never re-pushed; a `latest`
tag for humans only, never referenced by the CLI. Compose's default
`pull_policy: missing` then becomes a feature (no network on every start)
instead of the silent-staleness trap it is with mutable tags. Multi-arch is not
optional: **the reference floor itself is linux/arm64** (this host), so
`linux/amd64 + linux/arm64` from the first release, built and pushed in a single
`docker buildx build --platform ... --push` invocation — never per-arch jobs
pushing the same tag, which silently replaces the manifest list and produces
`exec format error` on the other architecture (documented incident class). CI
asserts both platforms are present via `docker buildx imagetools inspect` before
the release completes. Optional hardening: the CLI records the resolved
manifest-list digest at first pull and re-verifies on later starts.

**Registry: GHCR.** Docker Hub's 10 unauthenticated pulls/hour (since
2025-04-01) is disqualifying for a tool whose install path is anonymous pulls;
GHCR has no published pull quota, free public retention, repo co-location, and
`GITHUB_TOKEN` publishing.

**Release workflow: extend the existing one, ordered not atomic.** The Datasette
shape, on the same tag trigger the PyPI OIDC publishing already uses:
`test` → `pypi` (existing trusted publishing) → `image` (`needs: [pypi]`,
version from the same git tag, buildx multi-arch, login via `GITHUB_TOKEN` with
`packages: write`, cosign keyless signing of the pushed digest with
`id-token: write` — the image-side equivalent of the PyPI attestations). No
cross-registry atomicity exists anywhere; image-after-PyPI ordering makes the
only possible partial failure the detectable one (CLI on PyPI, image tag 404),
which the refuse-on-missing-image handshake surfaces with a clear error.

---

## 5. Q5 — the persona registry without hand-editing

Research verdict (full per-tool survey in the agent report; Aider, Continue.dev,
OpenCode, Cline, Goose, LiteLLM, OpenRouter, plus metadata registries):

- **Nobody in the field auto-assigns roles from capability metadata end-to-end.**
  Aider's weak/editor-model defaults come from a ~300-entry hand-curated table
  keyed by *known hosted-model names*; OpenCode outsources metadata to models.dev
  but the user still picks; OpenRouter's pure-auto router needed market-scale
  behavioral data and per-request granularity. The unoccupied ground is capability-
  flag→role assignment — and the likely reason it's unoccupied is that boolean
  flags can't express "strong enough to judge code."
- **Name heuristics on a gateway alias list are unreliable by construction** —
  LiteLLM aliases exist precisely so operators can name models whatever they want;
  `my-gpu-box-large` is the expected case. The reliable signals are the proxy's
  own metadata endpoint (`/model/info` on LiteLLM merges the same cost/capability
  map Aider uses; Ollama's `/api/show` returns a `capabilities` array; vLLM gives
  `max_model_len`) and a live probe of the alias itself.
- **The complaint class in every issue tracker is silent or unstable model
  assignment** (Cline #2501/#4187; Aider #3031/#5213), never "it asked me once at
  setup." Goose is actively migrating *from* implicit env-var magic *to* declared
  per-purpose config (block/goose#4036). Goose's wizard also live-probes
  credentials before writing config — accepted practice (LiteLLM's `/health` runs
  a real request per model).

**Recommended design — enumerate → enrich → rank → pre-filled picker → probe →
write only what passed:**

1. The install scan already enumerates aliases; add enrichment: LiteLLM-shaped →
   `/model/info` + `?return_wildcard_routes=true`; Ollama-shaped → `/api/show`;
   vLLM → `max_model_len`. Unclassifiable aliases are presented as "unclassified,"
   never ranked on vibes.
2. Rank per persona with a small legible requirements table (implementer: tools +
   largest context; judge: reasoning + structured output, and prefer independence
   from the implementer's alias; debugger: tools + reasoning; etc.).
3. Present a picker with the proposal and its *reason* pre-filled ("`qwen3-coder`:
   tools ✓, 262k ctx, cheapest of 3"), Enter to accept. `--yes` accepts
   probe-passing proposals for scripted installs.
4. **Probe before writing**, shaped per persona: implementer gets a forced
   tool-call; the judge gets a toy diff + criteria with a required JSON verdict —
   checked for parseability *and* for the correct verdict on a known-bad diff.
   A probe failure re-ranks; it never becomes write-with-warning.
5. **The never-silently-guessed line**: the judge, and every persona's *fallback*
   (fallbacks engage unwatched, mid-failure), always require explicit confirmation
   even under `--yes`; if nothing passes the judge probe, install fails loudly
   with the alias list and the unmet requirement — the existing `example/`
   rejection contract, kept, with better words.
6. **Scope: per-install.** The registry binds one gateway's private aliases plus
   write scopes and timeouts (partly security config) — committing that to a repo
   the factory rewrites is a double footgun. If per-repo steering is ever needed,
   let a repo declare *requirements* ("implementer needs ≥200k context") that
   install-scoped resolution satisfies; never a repo-committed alias.

This answers the §5c gap "story 4 is a sketch, not a design" — the above is
concrete enough to write the story against.

---

## 6. Q6 — the target repository's toolchain

Research verdict (devcontainer Features, mise/asdf, Nix, buildpacks, act, Bazel,
CI failure taxonomies — full survey in the agent report):

**Recommended: the mise pattern, provisioned at `ergane init`, into a per-repo tool
volume mounted read-only at gate time.**

- Bake mise (a few MB) into `ergane:X.Y.Z` with `MISE_DATA_DIR` pointed at a
  per-repo volume — mise reads the repo's *own* declarations (`mise.toml`,
  `.tool-versions`, `.nvmrc`, …) with no per-ecosystem knowledge in Ergane. This
  exact shape ships today (Citrix Secure Developer Spaces documents "one base
  image + mise reads each team's mise.toml"; GitHub Actions' setup-* + tool cache
  is the same pattern at scale).
- Provision at **`ergane init`**, not first gate run: the cold network cost lands
  once, while the operator watches — not mid-epic at attempt price. Gates then
  mount the tool volume read-only; gate runs stay network-free and deterministic.
- The repo's tool declaration is **agent-writable** — pin via lockfile, harden with
  `MISE_SAFE`-style settings, re-provision only at init or explicit refresh, never
  silently per-attempt.
- The boundary stated out loud: mise provisions *tools*, not system libraries.
  `libpq-dev`-class needs keep today's documented `FROM ergane:X.Y.Z` escape
  hatch. (Per-repo images built by Ergane — the buildpacks shape — is the better
  long-term hermetic answer but adds a builder, storage and invalidation machinery
  now, for one user. Nix was rejected: it excludes nearly every brownfield repo,
  and Railway just retreated from it.)

**Detection, not documentation**: adopt Bazel's discipline of making environment
failure a *distinct verdict* (Bazel exit 36 vs 3; exit 127 as the missing-binary
signal). A gate that dies with exit 127, or whose pre-gate `mise` probe reports
missing tools, must surface as "gate could not run: toolchain missing in the
sandbox (tool X, wanted by gate Y) — fix: `ergane init --refresh-tools` or extend
the image" — never charged to the story, never shown to the judge as a code
failure, never retried against the agent. This *preserves* the deliberate
no-gate-means-red friction: a repo with no declared gate still gets the impossible
gate; a repo whose declared gate can't run now fails legibly instead of failing
like bad code.

---

## 7. Q7 — the first run

Research verdict (fly, supabase, stripe, gh, k3d, flutter/react-native doctors,
scaffold-verb survey, worked-example literature):

- **Where people abandon**: interview-style wizards (fly rebuilt `launch` around
  inference-then-confirm because "first impressions matter"), long silent first
  runs (supabase's cold image pulls), and surprise cost (fly's accidental billed
  Postgres). Ergane's install interview already pre-fills from scans — keep
  moving it toward confirm-a-proposal rather than answer-questions (§5 is most of
  that). The money step — dispatch — must never be part of onboarding by default.
- **Doctor verbs read as helpful, not homework, iff**: every red line names its
  fixing command or auto-fixes (flutter/react-native are the archetypes); severity
  is honest; it runs automatically at the end of install and stays quiet when
  healthy (brew/expo are the crying-wolf anti-pattern). Ergane's
  `install --verify` + `doctor` already have the right bones; the finding-per-check
  shape should adopt "fix command on every red line" as a rule.
- **`ergane spec new` should scaffold a faded worked example, not a template**:
  the evidence (dbt's green-on-first-run scaffold; GitHub starter workflows; the
  worked-example effect, one of the most replicated results in learning science)
  says the first spec should *pass `spec validate` structurally as generated* —
  one tiny fully-worked story with a real resolving file:line anchor picked from
  the target tree at scaffold time, one illustrative trap, later story slots
  progressively skeletal, and every mandatory blank carrying a grep-able
  `ERGANE-TODO:` sentinel that `spec validate` reports with file:line as "not
  ready to derive." Structurally valid so the first validate teaches; not
  dispatchable as-is, so the no-vacuous-green ethos holds.
- **Collapse validate→derive→start into one verb the terraform way**: a superset
  verb (working name `ergane build ship <spec-dir>`) that streams each stage's
  full labeled output, stops at first failure, prints the compiled-graph summary
  after derive, and **pauses for confirmation before dispatch** (`--yes` for
  automation) — because dispatch spends real money and that pause is structurally
  where pre-dispatch refinement lives. The three constituent verbs survive for CI
  and debugging, exactly as `terraform plan` survives `apply`.
- **Install should end by doing something real that is fast, free and local** —
  and *not* an agent dispatch: run the doctor pass, then scaffold a throwaway
  one-story spec in a temp repo and take it through `init` + `spec validate` +
  `spec derive`, showing the compiled graph — a real artifact of the factory's
  actual loop, in seconds, at zero LLM spend. End mid-conversation with the next
  command verbatim (`ergane spec new` against their real repo), not a "ready"
  banner.

---

## 8. Named failure modes of the §5b design not in the brief

The brief asked for these as the highest-value output. In rough order of cost:

1. **bwrap-as-root silently takes the wrong path.** If the engine container ever
   runs as root (the compose default), bwrap doesn't fail at the userns layer the
   preflight would check — it fails at `clone(CLONE_NEWNS)` needing
   `CAP_SYS_ADMIN`, with the same EPERM text. A preflight built against the
   non-root assumption passes; the deployed container run as root fails. Pin
   `user:` in the generator and assert non-root in the preflight.
2. **bwrap as container PID 1 fails, with a misleading error** (`setting up uid
   map: Permission denied`). Any healthcheck or preflight that `docker run`s bwrap
   directly as the entrypoint reports a false negative against a config that is
   actually fine. `init: true` in the generated compose; preflight execs bwrap as
   a child.
3. **Config F's hidden host dependency**: the `bwrap` AppArmor stub is not stock
   Ubuntu 24.04 — it is hand-installed on the reference floor and unowned by any
   package. A fresh Ubuntu host running the F recipe fails at uid_map with no
   obvious cause. Either ship config G (no dependency on the stub) or make the
   installer own the stub file explicitly. **The native tier shares this
   dependency today, undocumented.**
4. **`apparmor=unconfined` + Ubuntu ≥23.10 is a trap in general**: removing the
   profile activates the kernel's capability-stripping `unprivileged_userns`
   transition. Any future "just turn AppArmor off to debug it" advice makes
   things worse. Document it; prefer named profiles always.
5. **The Temporal-history-outside-the-state-root recreate trap** (brief appendix,
   confirmed worth restating as a story-2 acceptance criterion): `compose down &&
   up` must provably preserve workflow history, asserted by `install --verify`.
6. **Stale-engine accumulation as the upgrade residue** (Dagger's ~600 GB lesson,
   Supabase's stale containers): `ergane worker deploy <rev>`-as-image-tag must
   also garbage-collect superseded images/containers, or the encapsulation pitch
   decays into "mystery disk usage."
7. **The health gate becomes the front door** (four years of Supabase's tracker):
   every startup race in the image becomes a CLI bug report. Generated compose
   needs healthchecks + a scriptable readiness verb + idempotent re-entry
   (`install` re-run against a half-up stack must converge, not error).
8. **The seccomp file is a fork of a moving upstream — and upstream is not
   about to absorb the delta.** The relaxation has been requested since 2021
   (moby#42441, still open) with unmerged 2025 PRs against moby/profiles;
   meanwhile moby *tightens* the profile between releases (AF_ALG blocking in
   29.4.x). Vendor the chosen profile with its upstream version recorded and
   re-diff on bumps — never regenerate-from-latest silently. The
   lower-maintenance option: adopt containers/common `seccomp.json` (podman's
   maintained default, which already carries exactly this delta) instead of
   hand-patching moby's.
9. **arm64 is not the exotic arch here — it is the reference floor.** This host is
   aarch64; an amd64-only image cannot run the factory that built it. Multi-arch
   (linux/amd64 + linux/arm64) from the first release, digest-pinned per arch.
10. **Gate toolchain invisibility is *worse* under §5b than under a plain
    container** because everything else feels native (§6's mise pattern +
    distinct environment-failure verdict is the mitigation).
11. **The `docker` group is an unstated root-equivalence grant.** The trust pitch
    ("it cannot wreck my machine") must not imply the opposite of reality:
    rootful Docker access is host-root-equivalent, and the *container's* sandbox
    hygiene doesn't change that. Either document it honestly, or (future) offer
    rootless podman as the paranoid tier — it is materially friendlier to this
    workload anyway (permissive-by-default seccomp, per-path `unmask=`,
    `--userns=keep-id` for uid mapping), at the cost of compose-compatibility
    caveats and a different state layout.
12. **Any non-bind view of the state directory corrupts.** The one real same-host
    SQLite corruption case in the wild was bwrap's *overlay* feature giving
    sandboxes divergent copy-on-write views of the same files. The invariant: the
    state directory crosses every boundary as a plain bind of the same directory
    (`.db` + `-wal` + `-shm` together) — no overlays, no copies, no sync layers,
    no single-file mounts, and no host-side `immutable=1`/`nolock=1` opens
    against a live engine. Worth a `spec validate`-style check in the compose
    generator and a line in the constitution's orbit if it ever recurs.
13. **A half-released version must fail in the detectable direction.** With PyPI
    and GHCR there is no cross-registry atomicity; publish the image strictly
    after PyPI (`needs:` ordering) so the only possible partial state is "CLI
    exists, image 404" — which the refuse-handshake reports clearly — never the
    silent inverse.
14. **The masked-/proc failure class is kernel-dependent and currently
    invisible.** `bwrap --proc` inside a container is documented to fail on
    some kernels (fully-visible rule; bubblewrap#284) and passed cleanly on
    this one (6.17). A preflight that skips the `--proc` mount — or that runs
    on a different kernel than the engine will — reports the wrong answer.
    The preflight must run the *full* production mount set inside the *actual*
    engine container.

---

## 9. The brief's "what would change our mind" items, answered

- *"bwrap inside Docker cannot be made safe or reliable without effectively
  disabling confinement"* — **false on the evidence**: narrow seccomp + named
  AppArmor profile + non-root + cap_drop ALL + no-new-privileges is far from
  disabled confinement, and the assumed-necessary double-unconfined isn't even
  sufficient.
- *"host-CLI-reads-container-SQLite is fragile in practice"* — **false on Linux**
  (measured), **true off Linux** (documented). The promise "operates as if
  native" holds verbatim on the Linux container tier; a macOS tier needs the
  engine-API read path and honest rewording.
- *"version drift worse than the systemd install's problems"* — **avoidable**: the
  derive-and-refuse contract (§4) is *stronger* than what the native tier has
  today (nothing stops a stale native worker; the image tag mechanically can't
  drift from the CLI that pulled it). Drift risk concentrates in the upgrade
  path's cleanup, which is a designable surface.
- *"a materially simpler shape exists"* — **yes, and it's already built**: the
  native tier. The simplification is not "don't containerize" but "don't make the
  container the default Linux path." The container earns its place on
  containment, removability, and non-systemd hosts — which is exactly the
  operator's trust language, honestly scoped.

---

## Appendix A — experiment log (all runs 2026-08-23, this host)

| Config | Flags (beyond `--rm`) | unshare -U -r | bwrap minimal | bwrap full Ergane mount set |
| --- | --- | --- | --- | --- |
| 1 default (root) | — | EPERM (seccomp) | EPERM clone | EPERM clone |
| 2 (root) | seccomp=unconfined | **OK** | EPERM `clone(CLONE_NEWNS)` | same |
| 3 (root) | apparmor=unconfined | EPERM (seccomp) | EPERM | EPERM |
| 4 (root) | both unconfined | uid_map EPERM (unprivileged_userns) | EPERM clone | EPERM clone |
| 7 (root) | --privileged | OK | OK | OK (ceiling only) |
| A | --user 1000 | EPERM (seccomp) | EPERM | EPERM |
| B | --user 1000, seccomp=unconfined | OK | `Failed to make / slave` (AppArmor mount deny) | same |
| C | root, --cap-add SYS_ADMIN | OK | `Failed to make / slave` | same |
| E | --user 1000, **narrow seccomp**, docker-default AppArmor | OK | `Failed to make / slave` | same |
| **F** | --user 1000, narrow seccomp, apparmor=unconfined | uid_map EPERM (expected; not bwrap's path) | **OK** | **OK** |
| F+harden | F + `--init` + `cap_drop ALL` + `no-new-privileges` | — | **OK** | **OK** (incl. git worktree commit + network egress) |
| **G** | F but apparmor=ergane-engine (operator-loaded) | OK | **OK** | **OK** (incl. git worktree commit, network egress, concurrent SQLite; child labeled `ergane-engine (enforce)`) |

Key single-purpose findings: strace pinned config-2's failure to
`clone(child_stack=NULL, flags=CLONE_NEWNS|SIGCHLD) = -1 EPERM`; the F sandbox
child's label is `bwrap (unconfined)` with `CapEff: 0` and nested bwrap refused;
direct-entrypoint bwrap fails uid_map, fixed by `--init`; SQLite concurrent
writers 3000+3000 commits, 0 busy, integrity ok; host↔container git worktree
round-trip clean at identical absolute paths.

## Appendix B — runnable artifacts

Also on disk (session scratchpad) at
`/tmp/claude-1000/-home-admin-code-ergane/7d769fe8-eb9f-4e94-a560-d35dd235a6fc/scratchpad/bwrap-exp/`:
`Dockerfile` (ubuntu:24.04 + bubblewrap + python3), `matrix.sh`, `matrix2.sh`,
`default-seccomp.json` (moby v28.3.3), `narrow-seccomp.json`,
`ergane-engine.profile`, `verify-config-g.sh`.

**narrow-seccomp.json construction** (the entire delta from moby default):

```text
1. Remove the rule: {names: [clone3], action: SCMP_ACT_ERRNO, excludes: {caps: [CAP_SYS_ADMIN]}}
2. Append:          {names: [unshare, clone, clone3, mount, umount2, pivot_root, setns],
                     action: SCMP_ACT_ALLOW}
```

(A later hardening pass can arg-filter `clone` to the CLONE_NEW* set bwrap uses
and drop `setns`; this shape is the verified baseline.)

**ergane-engine.profile** (verified 2026-08-23):

```text
abi <abi/4.0>,
#include <tunables/global>

profile ergane-engine flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  network,
  capability,
  file,
  umount,

  # deltas from docker-default: bwrap's namespace setup
  userns,
  mount,
  pivot_root,

  signal (receive) peer=unconfined,
  signal (receive) peer=runc,
  signal (receive) peer=crun,
  signal (send,receive) peer=ergane-engine,

  deny @{PROC}/* w,
  deny @{PROC}/{[^1-9],[^1-9][^0-9],[^1-9s][^0-9y][^0-9s],[^1-9][^0-9][^0-9][^0-9/]*}/** w,
  deny @{PROC}/sys/[^k]** w,
  deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/kcore rwklx,

  deny /sys/[^f]*/** wklx,
  deny /sys/f[^s]*/** wklx,
  deny /sys/fs/[^c]*/** wklx,
  deny /sys/fs/c[^g]*/** wklx,
  deny /sys/fs/cg[^r]*/** wklx,
  deny /sys/firmware/** rwklx,
  deny /sys/devices/virtual/powercap/** rwklx,
  deny /sys/kernel/security/** rwklx,

  ptrace (trace,read,tracedby,readby) peer=ergane-engine,
}
```

**Verification run (2026-08-23, operator-loaded profile)**: all probes passed —
P1–P3 OK, sandbox child labeled `ergane-engine (enforce)`, and the heavyweight
suite (git worktree commit from inside the sandbox, network egress, concurrent
host+container SQLite) re-passed under G. Config G is the recommended shipping
configuration; config F remains the documented fallback for hosts where loading
a profile is unacceptable.
