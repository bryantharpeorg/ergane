# The container onramp, planned end to end

**Written**: 2026-08-23, evening, by the operator session that produced
`docs/container-onramp-research-findings.md`. That document is the evidence base
for every decision below; this one is the plan. The operator's directive, verbatim
priority: **ease of install first — a developer runs the container as if it were
fully configured, with much faster setup.**

**Status of each piece** is tracked by its spec's own frontmatter, not here
(`ergane spec list specs` is the live answer). This page records the *shape* of
the program: what ships, in what order, and which decisions are already made so
no refinement pass re-derives them.

---

## The target, stated as the commands a developer types

```
uv tool install ergane-cli        # host, small, fast
ergane install                    # one interview; ends with a RUNNING, CONFIGURED,
                                  #   VERIFIED factory in a container — personas included
cd ~/code/my-project
ergane init .                     # joins the repo, adds its mount, engine picks it up
ergane spec new my-feature        # a scaffold that passes validate as generated
ergane build ship specs/103-my-feature   # validate → derive → confirm → dispatch
```

Five commands, one of which is `cd`. Nothing on this path asks the developer to
hand-edit YAML, stand up a subsystem, or learn compose. The container is the
developer onramp; the native systemd path remains, unchanged, for operators who
want control over each seam — the two share every verb, every config file and
every state layout, and differ only in who supervises the three processes.

## Decisions already made — do not reopen at refinement

Each traces to the findings document (§ references are to it).

1. **The sandbox inside the container is bwrap, under config G.** Verified on
   this host 2026-08-23: non-root engine user + `init: true` + `cap_drop: ALL`
   + `no-new-privileges` + narrow seccomp (moby default + 7 syscalls) + the
   `ergane-engine` AppArmor profile, with the sandbox child provably staying
   confined (`ergane-engine (enforce)`). No `--privileged`, no added
   capabilities, no `unconfined` token anywhere in the shipped artifacts.
   Config F (`apparmor:unconfined` + the host bwrap stub) is the documented
   fallback for hosts where loading a profile is unacceptable. (§1)
2. **The engine container runs as the host user's uid:gid**, with `HOME` set by
   the entrypoint into the mounted state tree. This is simultaneously what puts
   bwrap on its working code path and what makes every state file host-owned.
   (§1 blocker 2, §3)
3. **State crosses the boundary as plain same-path bind mounts** — the state
   root *and the supervision home* (the Temporal SQLite history lives there,
   one level above the supervision subdirectory — losing it on recreate is
   failure mode 5). Same absolute path inside and outside, always: repos,
   worktrees, state, config. No named volumes for state, no overlays, no
   copies, no syncs (failure mode 12). Host CLI keeps reading the SQLite
   stores directly — measured safe on Linux. (§3)
4. **Version contract: derive and refuse.** `ergane-cli X.Y.Z` runs
   `ghcr.io/bryantharpeorg/ergane:X.Y.Z` — the tag is a pure function of the
   CLI version, tags are immutable, `latest` is for humans only. On mismatch
   the CLI refuses with the remedy printed. Upgrade is an explicit drain-first
   verb, never a side effect. Multi-arch (amd64 + arm64) from the first
   release in a single buildx push — **the reference floor itself is arm64**.
   Registry is GHCR; the image job runs `needs: [pypi]` in the existing
   release workflow. (§4)
5. **Personas are proposed, probed and confirmed — never silently guessed.**
   Enumerate the gateway, enrich with whatever metadata endpoint it has, rank
   against a per-persona requirements table, present a pre-filled picker, live
   probe what was chosen (the judge's probe includes a known-bad toy diff), and
   write only what passed. The judge and every persona's fallback require
   explicit confirmation even under `--yes`; if nothing passes the judge probe,
   install fails loudly. Scope is per-install. (§5)
6. **The deliberate gate friction survives untouched.** A repo that declares no
   gate still gets the gate that cannot pass. The new, adjacent rule: a gate
   that cannot *run* (toolchain missing in the sandbox) is a distinct verdict,
   named as an environment failure, never charged to the story or shown to the
   judge as a code failure. (§6)
7. **Install ends by doing something real that is fast, free and local** — a
   doctor pass and a scaffolded throwaway spec taken through validate + derive,
   never a dispatch. Dispatch spends money; onboarding must not. (§7)
8. **The container is not the only tier, and the docs never present a
   symmetric menu.** One recommended default per context, one-sentence
   exception rule. The developer onramp leads with the container because
   encapsulated-and-removable is the promise being sold; the native path is
   the operator's tier. (§2)

## The specs, in dependency order

```
088  the whole factory fits in one container          (rewritten 2026-08-23)
      preflight that executes ─ supervisor ─ image + committed security
      artifacts ─ systemd verbs refuse by name
        │
        ├── 104  install brings the container up configured
        │         backend choice ─ compose project generation ─ bring-up,
        │         readiness, verify-through ─ init adds mounts ─ teardown
        │
        └── 105  the CLI and the image share one version
                  release workflow publishes multi-arch to GHCR ─ engine
                  version handshake ─ drain-first upgrade verb

103  install proposes personas and proves them        (independent of 088;
      scanner enrichment ─ ranking ─ picker ─ probe    critical for "fully
      before write)                                    configured"; benefits
                                                       the native tier too)

106  a first spec scaffolds, validates and ships      (independent; `spec new`,
      `build ship`, install's closing smoke)           smoke depends on 103+104
                                                       landing for full effect)

(parked, prototype-gated)  toolchain volumes: mise provisions the target
      repo's declared tools into a per-repo volume at `ergane init`, mounted
      read-only at gate time. Blocked on one experiment: mise under the
      read-only system tree inside the gate sandbox. Not numbered until the
      prototype answers. (§6)
```

**What can dispatch in parallel**: 088 and 103 immediately and concurrently —
they share no files. 106's `spec new` and `build ship` stories are also
independent of both. 104 needs 088 **merged** (it generates the project that
runs 088's image and supervisor). 105 needs 088's image to exist; its workflow
story can land earlier but proves itself only at the next release cut.

## What stays operator-manual, and why

- **The sudo moment.** Loading `ergane-engine` into the kernel is one
  `apparmor_parser -r` and requires root. `ergane install` prompts for it once,
  interactively, with the profile text on screen — an install that edits kernel
  security policy silently would betray the trust pitch it exists to make. A
  declined prompt falls back to config F with the difference stated. (104)
- **The release cut.** Agents author the workflow file; only a real tag proves
  it. The 0.4.0 cut is the verification step for 105's workflow story.
- **The watched end-to-end run.** A green suite and a PASS verdict are
  evidence, not proof. One real story, dispatched inside the container against
  a scratch repo, watched to a landing — the operator's step, after 104.
- **Two portability confirmations**, cheap, whenever convenient: the probe
  matrix on an x86_64 box, and config G on a stock Ubuntu 24.04 (no
  hand-installed bwrap stub — G is predicted to pass there; F is predicted to
  fail, which is why G ships).

## What this program deliberately does not include

- **A macOS tier.** Condemned-by-evidence for the shared-SQLite pattern
  (findings §3); when it comes, it is engine-mediated reads behind the seam the
  findings name — designed then, not retrofitted now.
- **Podman.** Materially friendlier to nested sandboxing, and the right
  back-pocket answer if Docker's posture worsens; not worth a second runtime
  matrix today.
- **One-container-per-agent-node.** Rejected while bwrap-under-config-G holds:
  it relocates the trust problem to the orchestration layer where every known
  answer (docker.sock, DinD, sysbox) is worse. Revisit only if G fails on
  stock hosts.
- **Smoothing the impossible gate.** Constraint, not oversight.
