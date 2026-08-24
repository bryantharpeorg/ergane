---
state: draft
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
#     (factory/cli/install.py:836-852, _apply_temporal_mode at :1114).
#   - The generated project derives from 088's committed reference
#     (container/compose.reference.yaml) and its confinement artifacts —
#     shared constants, drift-tested, so the reference and the generator
#     cannot disagree.
#   - The sudo moment is interactive and explained, never silent: loading
#     container/ergane-engine.profile edits kernel security policy, and an
#     installer that does that quietly betrays the trust pitch. Declining
#     falls back to config F with the difference stated (findings §1).
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
  reconciles the running engine (US5), so joining a repo stays one command.
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
   **Then** the backend defaults to `none` (configure only) and their
   existing tests pass unmodified.

### User Story 2 - The generator emits the compose project (Priority: P1)

As the container backend, I generate the full compose project from the
confirmed config and the repo registry — never asking the developer to edit
what I emit.

**Acceptance Scenarios**:

1. **Given** a confirmed config and a registry with two repos, **When** the
   generator runs, **Then** the project under the supervision home carries
   same-path mounts for the state root, the supervision home, the config
   directory and both repos, the confinement artifacts beside it, and env
   passthrough for the five subsystem blocks — proven by committed tests
   over the generated text.
2. **Given** a second run with nothing changed, **When** the generator runs,
   **Then** the output is byte-identical — idempotence proven by test.
3. **Given** 088's reference compose and the generator's constants, **When**
   the drift test compares them, **Then** service shape and security options
   agree — one fact, two files, one test.

### User Story 3 - The consent step loads the profile (Priority: P1)

As an operator, I see the AppArmor profile text and am asked before install
touches kernel policy; declining still leaves me a working, honestly
described engine.

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

### User Story 4 - Bring-up, readiness and verify-through (Priority: P1)

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

### User Story 5 - `ergane init` reconciles the engine (Priority: P2)

As a developer joining a repo, `ergane init .` remains one command: it
registers, regenerates the mounts, and the engine picks the repo up.

**Acceptance Scenarios**:

1. **Given** a running container engine, **When** `ergane init .` registers
   a new repo, **Then** the mount list is regenerated with the repo at its
   own path and the engine is reconciled — proven through seams.
2. **Given** the supervisor's same-path refusal (088 FR-009), **When** it
   fires under this backend, **Then** its remedy names this verb.

### User Story 6 - Uninstall unplugs cleanly (Priority: P2)

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
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
US4:
  implements: []
  depends_on: []
  depends_on_merged: [US2, US3]
US5:
  implements: []
  depends_on: []
  depends_on_merged: [US4]
US6:
  implements: []
  depends_on: []
  depends_on_merged: [US4]
```

## Requirements (summary — numbered at refinement)

Backend question + Docker detection; generator idempotence and
reference-derivation; consent-gated profile load with F fallback; bounded
readiness naming address and timeout; verify-through with engine left up on
failure; init-time mount reconciliation; teardown symmetry; **no
`unconfined` token in any generated file on the consent path**; the
generated project's file states it is generated and by what version.

## Success Criteria (summary)

Pasted transcripts: the full interactive install ending in a passing
verify-through; the declined-consent path generating F with the stated
difference; a second `ergane init` regenerating mounts and the engine
picking the repo up; uninstall leaving state but no project. The operator's
independent verification: one real story dispatched inside the engine,
watched to a landing.

## Assumptions

- 088's artifacts exist and are drift-tested; 103's persona step, when
  landed, slots into the same interview without contract change; 105 owns
  pull-by-version — until it lands, US4's local-build bootstrap is the
  documented path.
- Docker Compose v2 is present where Docker is (`docker compose`, not
  `docker-compose`); the probe that detects the daemon names the missing
  piece when only the legacy binary exists.
