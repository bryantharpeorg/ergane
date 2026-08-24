# Research brief: the containerized developer onramp for Ergane

**For**: a fresh research session. Assume **no access to the Ergane repository** —
everything needed to reason is in this file, including the code facts in the
appendix.

**Deliverable**: a recommended configuration, with reasoning and sources, good
enough for us to finalise or abandon the design in §5. Where the evidence is
thin, say so rather than picking.

**Written**: 2026-08-23, against Ergane 0.3.0.

---

## 0. How to use this brief

Read §1–§6 for context and constraints, then spend your effort on §7 — the open
questions. They are ordered by how much a wrong answer would cost us. Q1, Q4 and
Q5 are the ones where we are guessing; Q2 and Q7 are where prior art probably
already knows better than we do.

We are not looking for a summary of container basics. We are looking for the
specific configuration that survives contact with real developers, and for the
failure modes of the approach in §5 that we have not thought of.

---

## 1. What Ergane is, in enough detail to reason about it

Ergane is an agentic software factory: specs go in, merged and verified code
comes out, and no production code in the repository is written by a human.

The mechanism, briefly:

- An operator writes a **spec** — three markdown files (`spec.md`, `plan.md`,
  `tasks.md`) in a numbered directory — that declares user stories and a
  dependency graph between them.
- A **Temporal** workflow compiles that spec into a graph and dispatches each
  story to a coding agent running in **its own git worktree**.
- The agent's work is measured by **gates** — deterministic commands the target
  repository itself declares (e.g. `uv run pytest`) — and then scored by an
  **LLM judge** against the spec's acceptance scenarios.
- What passes goes through a **merge queue** on the forge (GitHub today) and
  lands on a buildout branch.

Five external things it needs, all declared in one `config.toml` with a typed
parser: an **LLM gateway** (LiteLLM-shaped, or a direct provider endpoint), a
**memory** backend, **Temporal**, **telemetry** (OTLP or none), and an
**escalation** channel (Telegram or webhook). Each is "bring your own" or
managed.

Three long-lived processes: the **Temporal server**, the **worker** (which runs
the workflows and spawns agents), and a **notify bridge** (turns a button press
in the escalation channel back into a workflow signal).

Agents are sandboxed with **bubblewrap** (`bwrap`) — an unprivileged-user-
namespace sandbox. Each agent sees its own worktree, a factory-owned per-node
`HOME`, and a read-only system tree. Gates run inside the same boundary.

Distribution today: `uv tool install ergane-cli` from PyPI, then `ergane
install` (an interactive interview that writes `config.toml` and verifies each
subsystem), then `ergane worker install` (which writes **systemd user units**),
then `ergane init` per repository.

---

## 2. The goal, in the operator's words

> "My ultimate goal is ease of getting from the install command to a fully
> functioning system, in as encapsulated a way as possible. I want devs to see
> it as an easy thing to get up and running and easy to trust because it's
> contained and durable back to disk."

and

> "I want it to operate all the same as if the dev has the things in the
> container actively running on his machine, but in a containerized form."

Three properties, in the operator's priority order:

1. **Short path from install to functioning.** Not "it starts." The next
   command a developer types after install should do real work.
2. **Encapsulated.** One thing to install, one thing to remove, no five-service
   prerequisite tour.
3. **Trustworthy because contained and durable.** A developer should believe
   (a) it cannot wreck their machine, and (b) it cannot lose their work.

---

## 3. The onramp we want

```
uv tool install ergane-cli          # host, small, fast
ergane install                      # host interview; ends with a running system
cd ~/code/my-project && ergane init .
<something that makes personas correct>
<one command that takes a written spec and starts building it>
```

Explicitly wanted:

- The **CLI lives on the host**. `ergane status`, `ergane findings list`,
  `ergane usage` run from the developer's own shell in their own repo, with no
  `docker exec` prefix. The container is where the engine runs, not a place the
  developer has to go.
- The developer's **source repositories stay on the host**, in their own
  editor, at their own paths.
- **Durable back to disk**: destroying and recreating the container loses
  nothing but uptime.

The two steps written as placeholders above are genuinely unresolved and are
research questions Q5 and Q7.

---

## 4. The onramp as it exists today

Accurate as of 0.3.0. `ergane --help` lists these nouns: `install`, `worker`,
`uninstall`, `init`, `spec`, `status`, `build`, `escalations`, `answer`,
`doctor`, `findings`, `usage`, `repo`, `roadmap`, `env`, `completion`.

The real sequence a new developer faces:

```
uv tool install ergane-cli
ergane install                 # interview: 5 subsystems -> ~/.config/ergane/config.toml
ergane install --verify        # probes each subsystem, reports one finding per check
ergane worker install          # writes + enables systemd user units
# edit ~/.config/ergane/personas.yaml by hand      <-- see below
cd ~/code/my-project
ergane init .                  # writes a committed manifest (ergane.yaml)
# author specs/NNN-name/{spec,plan,tasks}.md by hand
ergane spec validate <dir>     # frontmatter, work-graph and persona checks
ergane spec derive <dir>       # compile spec.md -> workgraph.json
ergane build start <epic-id>   # dispatch
#   ...or the roadmap route: `ergane roadmap start`, then
#      `ergane roadmap promote <spec>` to flip draft -> ready and let it dispatch
```

Three friction points on that path, all real:

1. **`personas.yaml` ships unconfigured.** The wheel includes an example
   registry whose model aliases are prefixed `example/`, and `install --verify`
   correctly reports that as a *failure*, not a vacuous pass. A developer
   finishes install with a factory that cannot dispatch until they hand-write a
   mapping from persona (`implementer`, `judge`, `architect`, `debugger`) to
   whatever model aliases their gateway actually serves.
2. **There is no `ergane spec new`.** No scaffold verb. Specs are authored by
   hand or via a separate Spec Kit toolchain.
3. **"Start building" is three commands**, or a different two if you use the
   roadmap scheduler.

One friction point that is **deliberate and must survive** any redesign: a
repository that declares no gate gets a gate that *cannot pass* — literally
`echo "ergane: declare gates.test in ergane.yaml" >&2; exit 1`. An earlier
version used `true`, a gate that cannot fail, and it silently reported green on
work nothing had looked at. Ease that hides an unverified green is the opposite
of trust. Do not propose smoothing this.

---

## 5. What we have designed so far

A spec (number 088) exists in draft. It was written to answer "what would it
take to ship this as `docker compose up`," and has since been reframed once by
the operator. Both versions are described, because the reframe is what we want
critiqued.

### 5a. First version — dev-owned compose

One container running all three processes under a Python supervisor; a
`Dockerfile` and a `compose.yaml` the developer owns and edits; the developer
passes endpoints in as environment variables.

**Why we moved off it**: nothing turned those environment variables into
`config.toml`. The typed config parser reads a TOML file, not the environment.
The headless install paths do not close the gap either — one refuses on any
field with no safe default (the LLM base URL is such a field), the other wants
a TOML the developer hand-writes. So `docker compose up` produced a *running*
system, not a *configured* one.

### 5b. Current version — `ergane install` owns the container

The reframe: **`ergane install` runs on the host and brings the container up as
part of installing.** It becomes a supervision backend, exactly parallel to the
systemd backend it already has.

```
uv tool install ergane-cli
ergane install     # interactive interview on the host
                   #   -> writes ~/.config/ergane/config.toml (host file)
                   #   -> pulls the version-matched image
                   #   -> generates a compose project (like it generates units today)
                   #   -> brings it up, then verifies through it
cd ~/code/my-project && ergane init .
                   #   -> registers the repo AND adds its mount
```

What this buys, and why we believe it is right:

- **The configuration problem disappears.** The interview runs on the host in a
  terminal. `config.toml` and `personas.yaml` are host files that get mounted
  in. No environment-to-TOML translation, no answers file to hand-author.
- **The CLI stays native.** Twelve modules read the factory's SQLite stores
  directly and six connect to Temporal, so a host bind mount plus a published
  port makes every read-only verb work from the developer's shell unchanged.
- **Versioned worker deploys survive.** Today `ergane worker deploy <rev>` puts
  a unit, a virtualenv and a checkout on the floor beside what is running. In
  container mode that becomes an image tag rolled beside the running service —
  same shape, different substrate.
- **Teardown stays Ergane's job**, which the project's portability principle
  requires: install into a brownfield repo, unplug cleanly, no lock-in.

Five stories, currently:

1. The sandbox preflight proves bwrap *runs*, not merely that it is installed.
2. A supervisor process inside the container, with everything durable on host
   paths.
3. `install` grows a container supervision backend that generates and brings up
   the project.
4. The persona registry gets written from what the install's endpoint scan
   found.
5. A version contract between the host CLI and the image.

### 5c. Where §3 (what we want) and §5b (what we planned) still diverge

| Wanted | Planned | Gap |
| --- | --- | --- |
| One command to functioning | `install` ends configured and running | Personas still need a source of truth — story 4 is a sketch, not a design |
| Sling a spec as the next step | Three commands, or the roadmap route | No scaffold verb; no single "build this spec" command |
| Trustworthy because contained | Compose file declares two `unconfined` security options | Reads as "we turned the sandbox off" — actively works against the pitch |
| Durable back to disk | Host bind mounts | Not yet proven; one durable path is easy to miss (see appendix) |

---

## 6. Hard constraints — not up for debate

Do not propose designs that violate these. They are settled, and several were
settled expensively.

- **The sandbox is bubblewrap.** The manifest key that selects it accepts
  exactly one value today. Dropping to an unsandboxed launch inside the
  container is rejected: several agent nodes run concurrently, and without the
  boundary they can read each other's worktrees, the shared SQLite stores and
  each other's per-node `HOME`.
- **Temporal is the orchestrator.** Not a job queue, not cron.
- **Gates are the target repository's own commands**, declared in its manifest.
  Ergane does not choose or infer what "green" means.
- **No human writes production code in this repository.** The factory builds
  its own features from specs. This is why the design has to be expressible as
  a spec, and why "just hand-write the Dockerfile" is not an available move.
- **Portability**: install into existing repositories, create new ones, and
  unplug cleanly. Users keep their specs. No lock-in.
- **Agent authentication is subscription-based**, never a raw provider API key
  handed to an agent.
- **The deliberate gate friction in §4 stays.**

---

## 7. Open questions, in priority order

### Q1. Can bubblewrap run inside Docker without disabling confinement?

**What we assume**: that on an Ubuntu 24.04 host, Docker's default AppArmor
profile plus the host's restriction on unprivileged user namespaces will block
`bwrap`, and that we will need `--security-opt apparmor=unconfined
--security-opt seccomp=unconfined`.

**Why it matters most**: it is unverified, and if true it directly undercuts
the trust pitch. A developer reading a compose file with two `unconfined` flags
concludes the sandbox is off. "Contained" is the word the operator used.

**What we want**:
- Is the assumption even correct on current Docker/Ubuntu? What exactly blocks
  it — AppArmor, seccomp, `kernel.apparmor_restrict_unprivileged_userns`, the
  `userns-remap` setting, or nesting depth?
- Can a **narrow custom profile** permit `unshare(CLONE_NEWUSER)` and the
  mount operations bwrap needs, without going fully unconfined? A concrete
  seccomp JSON and/or AppArmor profile would be the ideal answer.
- How do comparable projects solve nested sandboxing in containers — Nix
  sandboxed builds, Bazel, GitHub Actions runners, devcontainers, Firecracker-
  or gVisor-based approaches? Which of them actually run an unprivileged
  user-namespace sandbox *inside* an OCI container, and what do they require?
- Is `podman` (rootless, user-namespace-native) materially better here than
  Docker? What would we lose?
- Is there a defensible alternative shape — e.g. the agent sandbox being the
  container itself, one container per node — and what does it cost?

### Q2. Host CLI, containerized engine: what does the prior art teach?

**What we assume**: that a thin host CLI driving a containerized engine, with
state on host bind mounts, is a well-trodden pattern.

**Start here**: `truefoundry/trueforge` (MIT, ~3.7k stars as of 2026-08) ships
the exact deployment tiering we should interrogate — **local** is
`npx @truefoundry/trueforge`, single process, SQLite, no install and no
container; **docker compose** with Postgres and Redis is the *team* tier; and
Kubernetes is the hosted tier. Its README draws the line explicitly: "Local
mode is for your machine only." Note what that implies — they did **not** reach
for a container to make the easy path easy. Work out whether that tiering
generalises to a tool with Ergane's prerequisites, and what they gave up.

**What we also want**: concrete lessons from tools that do this — Supabase CLI,
LocalStack, Temporal's own dev server, Dagger, Tilt, Colima/Lima, the
devcontainer CLI, Testcontainers, Stripe CLI, Railway/Fly local emulators.
Specifically:

- How do they keep the CLI and the engine version-aligned, and what happens
  when a user upgrades one and not the other?
- Do they put state in named volumes or host bind mounts, and why?
- How do they handle the first-run experience — pull, health check, readiness?
- What do their issue trackers say is the most common way this shape confuses
  users?

### Q3. Durability and host-visible state

**What we assume**: bind-mounting the state directory to the host makes
everything durable and lets the host CLI read the same SQLite files the
container's worker writes.

**What we want**:
- Is SQLite over a Docker bind mount safe for concurrent access from inside and
  outside the container on Linux? WAL mode specifically. What are the real
  failure modes (locking, `flock` semantics over overlayfs/bind, `nobrl`)?
- How badly does this break on Docker Desktop for macOS/Windows (VirtioFS,
  gRPC-FUSE)? Is "Linux only, documented" acceptable, or is there a design that
  works everywhere?
- Is there a better pattern than "both sides open the same SQLite file" — e.g.
  the container exposing a small read API the CLI uses? What would that cost in
  latency and complexity?
- Any known issues with UID/GID mismatch between the container user and the
  host user for bind-mounted state and git worktrees?

### Q4. The version contract between host CLI and image

**What we assume**: `ergane-cli X.Y.Z` should pull `ergane:X.Y.Z`, and the CLI
should refuse when the running container disagrees with it.

**Why it matters**: this is a failure mode the current native install does not
have — two copies of the same code that can drift. This project has already
been bitten twice by a stale worker running code that no longer matched the
tree.

**What we want**:
- Refuse, warn, or auto-upgrade? What do comparable tools do, and what do their
  users complain about?
- Pin by tag or by digest? How do people handle multi-arch (arm64 Macs, amd64
  Linux) without accidental drift?
- Where should a small OSS project publish the image — GHCR, Docker Hub,
  both? The Python package already publishes to PyPI via OIDC trusted
  publishing; what is the equivalent good practice for images, and can one
  release workflow keep both in lockstep?
- Is there a pattern for "the CLI can upgrade the engine in place" that does
  not surprise someone mid-build?

### Q5. Making the persona registry correct without hand-editing

**Context**: a persona is a named role — `implementer`, `judge`, `architect`,
`debugger` — that resolves to a model alias, a write scope and a timeout. Code
never names a model; it names a persona. The registry is the only binding
between the two, and it ships as an example that install correctly rejects.

The install command already has two relevant capabilities: it **scans** for
reachable LLM endpoints and classifies them before asking (the scan is
advisory and pre-fills the answer), and it can **print the model aliases and
key-management endpoints the gateway must serve**.

**What we want**:
- Given a discovered LiteLLM-shaped gateway that can enumerate its models, what
  is the best way to propose a persona-to-model mapping? Heuristics on model
  name? A capability probe? Ask the user to pick per role from a list?
- What do comparable multi-model tools do for exactly this problem — Aider,
  Continue.dev, OpenCode, Cline, Goose, LiteLLM's own config, OpenRouter's
  routing? Which of them gets a good default without asking, and how?
- Where does the line sit between "helpfully guessed" and "silently wrong"?
  A wrong judge model produces plausible-looking verdicts, which is the
  expensive kind of wrong.
- Should the mapping be per-install or per-repository?

### Q6. The target repository's toolchain

**The problem**: gates run inside the container against a read-only system
tree, so a developer's host Go, Rust, Java or Node version is invisible to
them. `npm test` green on the host and red in the container, with no obvious
reason — and it is *more* surprising under the §5b design, because everything
else feels native. Our current answer is "write `FROM ergane:X.Y.Z` and add
your toolchain," which is a real cost.

**What we want**:
- How do devcontainer **features**, Nix, mise, asdf, or Docker's build cache
  make "add my toolchain to this base image" cheap enough that people actually
  do it?
- Is there a pattern where the container composes the target repo's declared
  toolchain automatically (e.g. reading `.tool-versions`, `mise.toml`,
  `flake.nix`, `.nvmrc`) without us maintaining per-ecosystem knowledge?
- Is "one image per target repository, built by Ergane on `ergane init`" saner
  than one shared image? What does that cost in build time and cache?
- How should the mismatch be *detected and reported* rather than merely
  documented? A gate that fails because the toolchain is absent should say so
  in those words.

### Q6a. Is the container the right lever for *ease* at all?

A challenge to our own framing, prompted by TrueForge (see Q2). On a Linux
host, Ergane's native path already has everything it needs: bwrap is a host
binary, the Temporal dev server is embedded and started from Python, the stores
are SQLite, git and the forge CLI are already installed. The container does not
obviously make that *easier* — it makes it **encapsulated, durable and
removable**, which is a different (and still valuable) promise.

If that is right, then ease has to come from `ergane install` doing more —
scanning, writing personas, scaffolding a first spec — and the container earns
its place on trust and teardown rather than on setup time. That would reorder
our five stories.

**What we want**: is there a defensible "local tier" for Ergane that skips the
container entirely on Linux, with the container as the portable/encapsulated
tier? What breaks on macOS, where bwrap does not exist at all and the container
stops being optional? Does a two-tier story confuse more than it helps?

### Q7. What does a genuinely good first-run look like?

**What we want**: the state of the art in CLI onboarding for tools with real
prerequisites. `gh`, `stripe`, `supabase`, `fly`, `vercel`, `turso`, `railway`,
`doctl`, `k3d`.

- Where do developers actually abandon these tools, and what fixed it?
- Is a `doctor`-style verify command the right shape, or does it read as
  homework? (Ergane has one, and a `--verify` flag on install.)
- Should install end by *doing something real* — a smoke build, a scaffolded
  example — rather than by printing "ready"? What are the failure modes of that
  (long first run, cost, confusion)?
- For a tool whose unit of work is a document the user has to write, what is
  the best scaffold? Is `ergane spec new` the right idea, and what should it
  produce so the first spec succeeds rather than teaching a bad habit?
- How should the "sling a spec" step collapse from three commands into one
  without hiding the validation that keeps bad specs from burning agent time?

---

## 8. What a good answer looks like

- **A recommended configuration**, concrete enough to write a spec against:
  which mounts, which security options, which volume shapes, which registry,
  which version-pinning scheme.
- **Sources.** Prefer primary — upstream docs, source, issue threads, release
  notes — over blog summaries. Date them; this area moves.
- **Explicit uncertainty.** Where the evidence is thin or contradictory, say
  which experiment would settle it. We can run experiments on the host; we
  cannot run them tonight in a chat.
- **Named failure modes** of the §5b design that we have not listed. This is
  the highest-value output. We would rather find them now than after the
  factory has built five stories.

## 9. What would change our mind

Say so plainly if any of these turn out to be true:

- bwrap inside Docker cannot be made safe or reliable without effectively
  disabling confinement — then the sandbox story needs a different shape, and
  we would want to know what shape.
- The host-CLI-reads-container-SQLite pattern is fragile in practice — then
  the CLI needs a different way to read state, and the "operates as if native"
  promise needs rewording.
- The version-drift problem between CLI and image is worse than the systemd
  install's problems — then containerizing may not be a net win for a developer
  onramp at all, and we should improve the native path instead.
- A materially simpler shape exists that we have not considered.

---

## Appendix: code facts you can rely on

Verified by reading the tree on 2026-08-23 at revision `838b9c3`. Cited so you
do not have to take the prose above on trust.

**Sandbox**
- The bwrap binary is pinned to the absolute path `/usr/bin/bwrap` in two
  places — the agent launcher and the gate executor. The pin is deliberate:
  Ubuntu 24.04's AppArmor profile permits unprivileged user namespaces only for
  the system binary at that path; a copied or vendored binary has no profile
  and fails with `EPERM`.
- The agent's mount set: `/usr` read-only, architecture-appropriate symlinks
  for `/bin`, `/lib`, `/lib64`, `/sbin`, plus `/proc`, `/dev` and a tmpfs
  `/tmp`. The node worktree is bound writable **at its own absolute path**. The
  environment is built, never inherited (`--clearenv`). Network is deliberately
  *not* unshared, so the agent can reach the gateway.
- The agent's toolchain is discovered at dispatch, not declared: the agent
  runner, `uv`, `node` and `git` must all resolve, or the dispatch refuses by
  name before forking.
- The host preflight currently decides bwrap is "usable" from `shutil.which`
  alone — i.e. presence, not execution. Inside a container those two differ for
  the first time. Fixing this is story 1 of the spec.

**State and durability**
- The factory state root holds three SQLite databases (a doctor/findings store,
  a usage ledger, a verification evidence store) plus directories for
  worktrees, transcripts, landing state and run state.
- **Twelve** modules open those SQLite files directly, including the `status`,
  `usage`, `doctor` and `findings` command surfaces. **Six** modules connect to
  Temporal.
- **Easy to miss**: the managed Temporal server's own SQLite history file lives
  under the *supervision home*, one directory above the supervision
  subdirectory — **not** under the factory state root. A container recreate
  that mounts only the state root would silently discard all workflow history.
- Git records absolute paths in `.git/worktrees/<name>/gitdir` and in each
  worktree's `.git` file, and the sandbox binds worktrees at their own paths.
  Mounting a repository at a different path inside the container produces
  worktree records that resolve on neither side.

**Configuration**
- `config.toml` lives at `~/.config/ergane/config.toml` by default and is
  parsed into five mode-discriminated blocks. Secrets are **not** in it: each
  block names the *environment variable* holding its credential.
- The persona registry defaults to `~/.config/ergane/personas.yaml`, falling
  back to package data in the installed wheel. A persona carries a name, an
  agent kind, an optional model alias, an optional fallback, a write scope and
  an optional timeout.
- The repo registry lives under a state home that defaults to
  `~/.local/state`, and is explicitly a **derived cache** — the committed
  per-repository manifest is the authority on membership.

**Supervision**
- `ergane install` (control-plane interview + verify) needs **no systemd**. The
  systemd units are written by a separate verb, `ergane worker install`.
- The one systemd coupling inside install: choosing "managed" Temporal is
  refused without a systemd user session, and the code names containers
  explicitly as a case where that session is missing.
- The install layout already carries a mode field for Temporal
  (`external` / `managed`), which is the precedent a supervision mode would
  follow.
- `ergane worker deploy <revision>` today creates a versioned unit, a
  virtualenv and a git checkout beside the running one.

**Distribution**
- Published to PyPI as `ergane-cli` (0.3.0) via OIDC trusted publishing.
  No container image is published today.
