---
state: draft
# DRAFTED 2026-08-25 ~11:05 PM CT by the operator session, against ergane-buildout
# at 5918ea5 (v0.4.0 shipped, 108 attested). Every file:line below was read from
# that commit on 2026-08-25 and verified against the tree before drafting.
#
# WHY THIS EXISTS. The operator asked for one command:
#
#     curl -fsSL https://…/ergane/compose.yaml | docker compose -f - up
#
# and named it the desired state for install. The measurement behind the ask is
# that v0.4.0 got most of the way there without anyone planning it: the engine
# image is published, multi-arch, signed, and it supervises its own Temporal.
# What is missing is narrower than it looks.
#
# THE OPERATOR'S RULING, taken 2026-08-25 after three options were put to him.
# The demo dispatches ONE story and STOPS BEFORE LANDING — it shows an agent
# writing code in a sandbox, a deterministic gate running, and a judge rendering
# a verdict. It does not land. The rejected alternative was a local git forge
# implementing the eight-method Forge protocol (factory/mergequeue/forge.py:178):
# it looks more complete and demonstrates less, because a forge that merges a
# branch with no merge queue and no required checks is showing `git merge`
# rather than a factory. Being explicit that landing needs a real forge is
# honest; faking it is not.
#
# Settled at drafting:
#   - THE DEMO PROJECT IS NOT GENERATOR OUTPUT. `ergane install` generates the
#     operational project and `_check_paths` (container_project.py:318-329)
#     REFUSES any bind where `mount.source != mount.target`, because git records
#     absolute paths in worktree files. That invariant protects a host CLI and a
#     container sharing worktrees. The demo has no host side — everything lives
#     in volumes — so the invariant is vacuous there, and a generator that
#     enforces it correctly cannot emit this file. Hand-authored artifact,
#     checked in, tested for drift. Two artifacts, two jobs.
#   - THE GATEWAY IS A COMPOSE SIBLING, NOT A FOURTH SUPERVISED CHILD. The
#     container already supervises three (container_supervisor.py:39-43) and a
#     fourth is mechanically easy. It is still wrong: LiteLLM key management
#     needs a DATABASE_URL, so bundling the gateway means bundling Postgres, and
#     a database inside the engine's restart policy makes every
#     `ergane engine upgrade` a migration. 105 built upgrade as a drain-first
#     verb precisely because the engine holds state; this keeps that blast
#     radius where it is.
#   - THE OVERRIDE MIRRORS `temporal mode` EXACTLY. `_ask_temporal`
#     (install.py:1764) asks `temporal mode (external|managed)`. The gateway asks
#     the same question the same way. A second override pattern for the same
#     class of decision is how the first one rots.
#   - ONE ENVIRONMENT VARIABLE, AND IT CANNOT BE REMOVED. `verify.py:415` records
#     that `gateway` is the only mode a parsed config can carry (048-US2), and
#     the LLM probe mints a short-TTL key, asserts it is model-constrained, reads
#     spend logs and revokes it (`:453-511`). An agentic factory cannot be
#     demonstrated without a model. One upstream key is the floor, not a
#     shortcut not taken.
#   - THE HALT IS A STATE, NOT A HACK. `NodeState` already runs
#     PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED → PR_OPEN → ENQUEUED →
#     MERGED (models.py:78), and `:86` records that PR_OPEN and ENQUEUED are
#     "the landing phase's states". A node at PASSED has run the agent, the gate
#     and the judge, and has not touched a forge. The seam exists; only the
#     switch is missing.
#
# CORRECTED BEFORE DRAFTING, so nobody repeats it: the shipped registry's
# placeholder is NOT `CHANGEME`. It is the `example/` prefix —
# `EXAMPLE_ALIAS_PREFIXES = ("example/",)` at factory/config.py:57, with
# `is_example_alias` at :76 and the refusal at verify.py:441. `CHANGEME` is a
# pytest fixture's stub model alias and a different thing entirely.
---

# Feature Specification: a stranger runs the factory in one command

**Created**: 2026-08-25
**Depends on**: 104, 105, 108 (all landed). US1 and US3 are independent of each
other; US2 needs US1's config shape; US4 needs US2's file to exist.

## The gap, stated precisely

`v0.4.0` shipped an engine container that is closer to self-contained than the
documentation admits. It is not a CLI wrapper — its entrypoint supervises three
children, and the first is a Temporal server:

```python
_CHILDREN: dict[str, str] = {
    "temporal": "factory.supervision.temporal_server",
    "worker": "factory.worker",
    "bridge": "factory.notify.service",
}
```

The image also carries `bubblewrap`, `git`, `gh`, `node 22`, `uv` and
`@anthropic-ai/claude-code`. A dispatched node's whole toolchain travels inside
it. Published size is 1.68 GB.

So the distance to a one-command demo is three things, and only one of them is
large:

1. **The gateway has no bundled half.** Nothing in `container/compose.reference.yaml`
   or in the supervisor provisions a LiteLLM proxy; `install.py` only ever talks
   to one through `LiteLLMClient`. Every other subsystem the container needs has
   an in-container answer. This one does not.
2. **The shipped registry cannot dispatch.** Its aliases carry the `example/`
   prefix, and `install --verify` refuses them by design (`verify.py:441`). That
   refusal is correct and must not be weakened; the demo needs a registry whose
   aliases the bundled gateway actually serves.
3. **Nothing publishes a compose file.** There is no URL to `curl`.

## The rule this spec is asking for

**A person who has never seen Ergane runs one command with one environment
variable set, and watches an agent write code in a sandbox, a deterministic gate
run over it, and a judge render a verdict — on their own machine, with nothing
installed but Docker.**

### What the demo is not

It does not land. It has no forge, opens no pull request, and merges nothing.
The epic reaches `PASSED` and stops there, and the reason is stated in the
output rather than left as an absence. A demo that fakes a merge teaches the
wrong thing about a system whose entire subject is what happens between "the
tests pass" and "the code is on the branch".

## User Scenarios & Testing

### User Story 1 - The gateway has a bundled half (Priority: P1)

As an operator installing Ergane, I am asked where the gateway comes from the
same way I am asked where Temporal comes from, and "bring your own" is an
answer rather than the only answer.

**Why this priority**: P1 and first. US2 assembles what this story makes
configurable, and the question's shape has to exist before anything can answer
it.

**Independent Test**: run the interview, choose each mode, and read the written
config back.

**Acceptance Scenarios**:

1. **Given** the install interview, **When** it reaches the gateway, **Then** it
   asks `gateway mode (external|managed)` — the same grammar `_ask_temporal`
   uses at `install.py:1764` — and both answers are accepted, proven by a
   committed test that runs the interview twice.
2. **Given** `mode = "external"`, **When** the config is written and verified,
   **Then** behaviour is exactly today's: the operator supplies `base_url` and
   `master_key_env`, and every existing LLM verification test passes
   **unmodified**.
3. **Given** `mode = "managed"`, **When** the config is written, **Then** it
   records the bundled gateway's address and the fact that the project owns its
   lifecycle — and `--from-file` accepts the same key, so a demo can select it
   without an interview (`install.py:1221`).
4. **Given** either mode, **When** `install --verify` runs, **Then** the
   key-management probe at `verify.py:453-511` runs unchanged — mint,
   model-constrain, read spend logs, revoke. A managed gateway is verified by
   the same evidence as an external one, never trusted because it is ours.

### User Story 2 - The demo project exists and is one file (Priority: P1)

As a stranger with Docker, the compose file I fetch brings up an engine, a
gateway and its database, configured, with no interview and no host paths.

**Why this priority**: P1. This is the artifact the operator asked for.

**Independent Test**: on a machine with no Ergane config, run the file with one
variable set and observe the stack come up healthy.

**Acceptance Scenarios**:

1. **Given** the committed `container/compose.demo.yaml`, **When** a drift test
   reads it, **Then** it declares exactly three services — the engine, a LiteLLM
   gateway and a Postgres for key management — and the engine's image reference
   derives from the same version source as `container/compose.reference.yaml:10`.
2. **Given** the same file, **When** the test reads its volumes, **Then** every
   one is a **named volume**, not a host bind, and **no** mount pair is
   same-path — the inverse of what `_check_paths` (`container_project.py:318`)
   demands of the operational project. A committed test asserts both facts and
   names the reason, so a future reader does not "fix" one into the other.
3. **Given** the file, **When** the test reads what it requires from the
   environment, **Then** exactly one variable is mandatory — the upstream model
   credential — and every other value has a working default baked in.
4. **Given** the project comes up, **When** `install --verify` runs inside it,
   **Then** it passes, including the key-management probe, using a bundled
   answers file (`--from-file`) and a registry whose aliases carry no `example/`
   prefix. **The shipped refusal at `verify.py:441` is not weakened**; the demo
   satisfies it rather than bypassing it.
5. **Given** a reader of the file, **When** they look for what it is not,
   **Then** a header comment states plainly that this project is a demonstration
   with volume-local state, that it does not land, and that
   `ergane install --engine=container` generates the operational project
   instead.

### User Story 3 - The epic halts at PASSED, and says so (Priority: P1)

As the demo, I run one story to a verdict and stop before the landing phase,
declaring the stop rather than appearing to hang.

**Why this priority**: P1, and independent of US1 and US2 — this is a workflow
change that the demo consumes but does not require to exist first.

**Independent Test**: dispatch a one-node graph in the halting mode against a
scratch repo with no forge configured, and observe the terminal state.

**Acceptance Scenarios**:

1. **Given** a graph dispatched in the halting mode, **When** a node passes its
   gate and its judge, **Then** its terminal state is `PASSED` and no forge call
   is made — proven by a committed test that fails the run if the forge seam is
   touched at all.
2. **Given** the same run, **When** it finishes, **Then** the output states that
   landing was **not attempted** and why, naming what would be required to land.
   An absent landing must never read as a failed one; `models.py:86` already
   distinguishes the landing phase's states from `PASSED`, and this makes the
   distinction visible to a human.
3. **Given** a normal dispatch with the mode off, **When** it runs, **Then**
   behaviour is exactly today's, through `MERGED` — proven by the existing
   workgraph tests passing unmodified.
4. **Given** the halting mode, **When** a node **fails** its gate or judge,
   **Then** it reports failure as it does today. The mode changes where success
   stops, never what failure means.

### User Story 4 - The file has a URL (Priority: P2)

As a stranger reading a README, the command in it works, because the release
that publishes the image also publishes the compose file that names it.

**Why this priority**: P2 by sequence — the file must exist before it can be
published — and it is the story that makes the operator's one-liner literally
true.

**Independent Test**: cut a tag, then fetch the published URL and diff it
against the committed file.

**Acceptance Scenarios**:

1. **Given** `.github/workflows/release.yml`, **When** a drift test reads it,
   **Then** a step publishes `container/compose.demo.yaml` as a release asset,
   and it runs **after** the image job — a compose file naming an image that
   does not exist yet is the same failure mode 105 ordered the pipeline to
   prevent.
2. **Given** the published asset, **When** it is fetched and read, **Then** its
   engine image tag equals the tag being released — proven by a step in the
   workflow that fails the release on mismatch, not by a human comparing.
3. **Given** the whole workflow, **When** the suite runs, **Then** every test
   105 and 108 landed passes **unmodified**, including the preflight ordering
   and the package linkage and visibility assertions.

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
  concurrent_with: [US1, US2]
US4:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

`concurrent_with` is declared on US3 because the validator's `slice_contention`
layer reads a task's **prose mentions** of a path as membership in that task's
slice, and US3's tasks necessarily name `container/compose.demo.yaml` (the
consumer of the mode it adds) and `factory/cli/install.py` (where the mode is
selected). US3 **edits neither** — it owns the workgraph workflow and its models.

Chain depth 3: US1 → US2 → US4, with US3 running alongside from the first round.

## Requirements (summary — numbered at refinement)

Gateway mode question, grammar and both answers; external mode unchanged;
managed mode's recorded address and lifecycle ownership; `--from-file`
acceptance; the key-management probe running identically for both modes; the
demo compose's three services; named volumes and the not-same-path assertion
with its stated reason; the single mandatory environment variable; the bundled
answers file and non-`example/` registry; the header comment naming what the
file is not; the halting mode's terminal state; the no-forge-call assertion; the
"landing not attempted" statement; unchanged behaviour with the mode off;
unchanged failure semantics; the release asset step and its ordering; the
published tag equalling the released tag, asserted in the workflow.

## Success Criteria (summary)

Pasted: the interview transcript for both gateway modes; the demo project coming
up and `install --verify` passing inside it, with the key probe visible; a
halting-mode run reaching `PASSED` with the landing statement quoted; the
existing workgraph and release suites passing unmodified with before-and-after
counts.

**Operator verification, which is the point of the spec**, run on a machine that
has never had Ergane installed:

```bash
export ANTHROPIC_API_KEY=…
curl -fsSL https://github.com/bryantharpeorg/ergane/releases/latest/download/compose.yaml \
  | docker compose -f - up
```

A stranger sees the stack come up, one story dispatched, an agent write code, a
gate run, a judge render a verdict, and a clear statement that landing was not
attempted. No `pip install`, no interview, no host paths, no GitHub account.
