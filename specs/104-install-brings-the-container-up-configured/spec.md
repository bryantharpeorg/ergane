---
state: ready
# DRAFTED 2026-08-23 ~10:15 PM CT by the operator session behind
# docs/container-onramp-program.md. Spec-only draft: plan.md and tasks.md are
# written at this spec's own refinement pass, once 088 has landed and its
# committed artifacts exist to be cited by line. Depends on 088 MERGED.
#
# The operator's directive, which this spec exists to satisfy: ease of
# install first — `ergane install` ends with a running, configured, verified
# containerized factory, and the developer never edits compose by hand.
#
# Settled at drafting:
#   - The generator is a supervision backend PARALLEL TO systemd units
#     (factory/supervision/units.py:716 is the precedent), selected in the
#     interview the way temporal.mode already selects managed/external
#     (_ask_temporal at factory/cli/install.py:1277, its apply= at :1286,
#     _apply_temporal_mode at :1555). Those three anchors were re-read on
#     2026-08-24; the drafting-day pair (:836-852, :1114) predated 103's
#     landing, which moved everything in that file down by ~440 lines.
#     plan.md's "What already exists" section is the current map.
#   - The generated project derives from 088's committed reference
#     (container/compose.reference.yaml) and its confinement artifacts —
#     shared constants, drift-tested, so the reference and the generator
#     cannot disagree.
#   - The sudo moment is interactive and explained, never silent: loading
#     container/ergane-engine.profile edits kernel security policy, and an
#     installer that does that quietly betrays the trust pitch. Declining
#     falls back to config F with the difference stated (findings §1).
#
# REPAIRED 2026-08-24 against an adversarial review of the trio. Five blocking
# findings closed, in plan.md: R4 (byte-equality against a hand-written,
# comment-carrying reference was unbuildable — now structural + comment
# agreement, with comments as data), R6 (its containment claim was false; the
# db is under the STATE-ROOT mount, and it must not be the native tier's own
# dev.db), R10 (new: container/ and Dockerfile reach no installed CLI — the two
# confinement artifacts become package data, the build context stays a
# checkout), R12 (new: TEMPORAL_ADDRESS carries two incompatible meanings and
# bring-up is the first path to hit it), and trap 14 (no committed transcript
# can be a real run in this sandbox — every one is a labelled seam capture).
# US2 was split: the writer is now US3 (R11), so the renderer's risk and the
# persistence layer fail separately. Stories renumbered; chain depth unchanged
# at 4.
---

# Feature Specification: install brings the container up configured

**Created**: 2026-08-23
**Depends on**: spec 088 merged. **Evidence base**: findings §1–§3, program
document decisions 1–3.

## The gap, stated precisely

After 088, the engine container exists, supervises itself and proves its
sandbox — but nothing *brings it up*. The reference compose is a reference; a
developer would copy it, fill in mounts and env names, load an AppArmor
profile by hand, and run `docker compose up` — five manual steps standing
where the operator's directive demands one. Meanwhile `ergane install`
already ends with a written `config.toml`, a seeded (after 103: written and
proven) persona registry, and a verify pass — everything the container needs,
sitting on the host, with no engine to hand it to.

## The rule this spec is asking for

**`ergane install`, having interviewed and configured, offers to run the
engine — and when the operator chooses the container, install generates the
compose project, loads the confinement profile with consent, brings the
engine up, waits for readiness, and verifies through the running engine. One
command in; a working factory out.**

### The ruling, made here rather than left to the implementer

- **A supervision backend, not a new tool.** The interview gains one
  question — where the engine runs: `container` (offered first when a Docker
  daemon answers) or `systemd` (today's path, unchanged) or `none`
  (configure only, today's exit). The container backend generates its
  project the way `ergane worker install` writes units; teardown removes
  what it generated, per the portability principle.
- **Generated, never hand-edited — and derived from 088's reference.** The
  generator and the reference compose share their constants (service shape,
  security options, mount rules) so the drift tests that pin the reference
  pin the generator too. The generated project lives under the supervision
  home; regenerating is idempotent.
- **The mounts come from the config and the registry, at their own paths.**
  State root, supervision home (Temporal history lives there — findings
  failure mode 5), config directory, and one entry per registered repo, all
  same-path. `ergane init` in container mode regenerates the mount list and
  reconciles the running engine (US6), so joining a repo stays one command.
- **The sudo moment is one prompt, with the profile text shown.** Consent
  loads `ergane-engine`; declining generates the config-F variant with the
  difference stated in the output and in the generated file's comments.
  Install never edits kernel policy silently.
- **Readiness is bounded and verified through the engine.** After up,
  install waits (bounded, address named) for Temporal's published port, then
  runs the same `--verify` battery the native path runs — the probes now
  exercising the *running container*, including 088's bwrap preflight from
  inside. A verify that fails tears nothing down: the engine stays up for
  diagnosis, and the failure names the remedy.

## User Scenarios & Testing

### User Story 1 - The interview asks where the engine runs (Priority: P1)

As an operator running `ergane install`, I am asked where the engine should
run — with the container offered first when Docker answers — and the paths I
do not choose are left exactly as they are today.

**Acceptance Scenarios**:

1. **Given** a host where a Docker daemon answers, **When** the interview
   reaches the engine question, **Then** `container` is offered first with
   `systemd` and `none` present, and choosing either of the latter leaves
   today's behaviour unchanged — proven by committed interview tests.
2. **Given** a host with no reachable daemon, **When** the operator chooses
   `container`, **Then** install refuses naming the daemon as missing and
   how to get it — proven by a committed test.
3. **Given** `--non-interactive` or `--from-file`, **When** they run,
   **Then** the backend defaults to `none` (configure only), their existing
   tests pass unmodified, and an explicit `--engine` passed alongside either
   flag is refused by name rather than silently ignored — proven by a
   committed test.

### User Story 2 - The generator emits the compose project (Priority: P1)

As the container backend, I render the full compose project from the
confirmed config and the repo registry — never asking the developer to edit
what I emit.

**Acceptance Scenarios**:

1. **Given** a confirmed config and a registry with two repos, **When** the
   generator runs, **Then** the project carries same-path mounts for the
   state root, the supervision home, the config directory and both repos,
   the confinement artifacts beside it, and env passthrough for the five
   subsystem blocks — proven by committed tests over the rendered text.
2. **Given** the same inputs twice, **When** the renderer runs, **Then** the
   rendered text is identical, because it is a function of the project data
   and nothing else — determinism proven by test.
3. **Given** 088's reference compose and the generator's one renderer,
   **When** the drift test compares them, **Then** the parsed structure and
   the comment lines agree — one fact, two files, one test.

### User Story 3 - The generated project is written, remembered and removable (Priority: P1)

As the container backend, I write what I rendered under the supervision home
and remember by digest what I wrote — so a re-run is a no-op, a hand edit is
never clobbered, and teardown removes mine and nothing else.

**Acceptance Scenarios**:

1. **Given** a rendered project and an empty project directory, **When** the
   writer runs, **Then** every file is written with its digest recorded in
   the manifest, and a second write leaves both the directory and the
   manifest byte-identical — proven by committed tests.
2. **Given** a file inside the project directory that the manifest does not
   claim, **When** the writer runs again, **Then** it refuses to overwrite
   that file naming it; **and When** removal runs, **Then** the unclaimed
   file survives while every file whose recorded digest still matches is
   removed — proven by committed tests.

### User Story 4 - The consent step loads the profile (Priority: P1)

As an operator, I see the AppArmor profile text and am asked before install
touches kernel policy; declining still leaves me a completely generated,
honestly annotated engine whose remaining prerequisites are named.

**Acceptance Scenarios**:

1. **Given** consent, **When** install loads `ergane-engine` through the
   injected privilege seam, **Then** the profile text was shown before the
   prompt and the generated compose names `apparmor=ergane-engine` — proven
   by a transcript test.
2. **Given** a decline, **When** generation proceeds, **Then** the config-F
   variant is generated with the difference stated in the output and in the
   file's comments, and no privileged command was attempted — proven by a
   committed test.
3. **Given** a failing `apparmor_parser`, **When** the load runs, **Then**
   install reports the error verbatim and falls back to F with the same
   statement — never a half-configured project.

### User Story 5 - Bring-up, readiness and verify-through (Priority: P1)

As an operator, my install ends with the engine running and verified — or
with the engine left up and a named remedy.

**Acceptance Scenarios**:

1. **Given** a generated project, **When** install brings it up, **Then** it
   waits bounded on the Temporal port naming address and timeout, then runs
   the verify battery against the running engine and reports per-subsystem
   findings — driven through injected process and port seams.
2. **Given** a failing verify, **When** install ends, **Then** the engine is
   left up for diagnosis and the failure names the remedy — proven by a
   committed test.
3. **Given** a half-up stack from an earlier attempt, **When** install
   re-runs, **Then** it converges rather than erroring — idempotent
   re-entry, proven by a committed test.
4. **Given** the one Temporal address convention this tree already uses
   (`host:port`), **When** the generated `.env` names it and the engine's
   supervisor reads it, **Then** both sides resolve the same endpoint and no
   port is appended twice — proven by a committed test over the supervisor's
   own parsing.

### User Story 6 - `ergane init` reconciles the engine (Priority: P2)

As a developer joining a repo, `ergane init .` remains one command: it
registers, regenerates the mounts, and the engine picks the repo up.

**Acceptance Scenarios**:

1. **Given** a running container engine, **When** `ergane init .` registers
   a new repo, **Then** the mount list is regenerated with the repo at its
   own path and the engine is reconciled — proven through seams.
2. **Given** the supervisor's same-path refusal (088 FR-009), **When** it
   fires under this backend, **Then** its remedy names this verb.

### User Story 7 - Uninstall unplugs cleanly (Priority: P2)

As an operator leaving, `ergane uninstall` takes the engine down and removes
what install generated — and nothing else.

**Acceptance Scenarios**:

1. **Given** a running engine, **When** uninstall runs under this backend,
   **Then** the engine goes down and the generated project is removed while
   the state root and config remain — proven by a committed test.
2. **Given** the existing purge semantics, **When** purge is chosen,
   **Then** they extend to the generated artifacts with each removal named,
   per 083's teardown grammar.

## Work Graph

```yaml
US1:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: []
US2:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: []
US3:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: [US2]
US4:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: [US2]
  concurrent_with: [US3]
US5:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: [US1, US2, US3, US4]
US6:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: [US5]
US7:
  persona: opus-closer
  implements: []
  depends_on: []
  depends_on_merged: [US5]
  concurrent_with: [US6]
```

US1 and US2 are concurrent: the plan's rulings R1 and R2 keep the backend
answer out of `config.toml` and out of the generator's module, so US1 asks a
question and holds a local while US2 renders text. US3 (the writer) and US4
(consent) both need US2's renderer merged and are concurrent with each other —
US3 owns a new persistence module and US4 owns the profile module plus one
parameter on the renderer, so the `concurrent_with` waiver states that the pair
was considered rather than missed. US5 wires the question, the renderer, the
writer and the consent decision together in one `install_command` branch. US6
and US7 both call the writer without editing it — the second waiver, for the
same reason.

## Requirements (summary — numbered at refinement)

Backend question + Docker detection; a deterministic renderer whose reference
render agrees with 088's committed file in structure and in comments;
digest-remembered writes and removals; consent-gated profile load with F
fallback; bounded readiness naming address and timeout; **one Temporal address
convention (`host:port`) on both sides of the mount**; verify-through with the
engine left up on failure; init-time mount reconciliation; teardown symmetry;
**no `unconfined` token in any generated file on the consent path**; the
generated project's file states it is generated and by what version.

## Success Criteria (summary)

Committed **seam captures** — transcripts taken through the injected process,
prompt and port seams, labelled as such: the install run ending in a passing
verify-through; the declined-consent path generating F with the stated
difference; a second `ergane init` regenerating mounts and the engine picking
the repo up; uninstall leaving state but no project. No committed criterion
requires a Docker daemon, a running container or `apparmor_parser` — those are
the operator's own verification list in `plan.md`, ending with one real story
dispatched inside the engine and watched to a landing.

## Assumptions

- 088's artifacts exist and are drift-tested; 103's persona step, when
  landed, slots into the same interview without contract change; 105 owns
  pull-by-version — until it lands, US5's local-build bootstrap is the
  documented path.
- **Until 105 publishes the image, the container tier requires a source
  checkout.** `Dockerfile:44` is `COPY . /opt/ergane` followed by an editable
  install, so the build context *is* the repository; a wheel install has none
  (`pyproject.toml:48-49` ships the `factory` package only). The generator
  refuses the local-build path by name when no `Dockerfile` sits at the install
  root, and names 105 as the fix. The two confinement artifacts are a different
  case and do travel in the wheel — see plan R10.
- **The container onramp requires a reachable LLM gateway.** The engine reads
  the persona registry, and `_interview_personas` (`factory/cli/install.py:516`)
  proves aliases against the confirmed gateway before that registry is written,
  raising `OperatorError` when it cannot. An install that cannot reach its
  gateway does not reach bring-up under any backend.
- Docker Compose v2 is present where Docker is (`docker compose`, not
  `docker-compose`); the probe that detects the daemon names the missing
  piece when only the legacy binary exists.
