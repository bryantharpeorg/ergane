# Implementation Plan: a stranger runs the factory in one command

**Spec**: `specs/109-a-stranger-runs-the-factory-in-one-command/spec.md`
**Base**: `ergane-buildout` at `5918ea5` (v0.4.0 shipped, 108 attested). Every
`file:line` below was read from that commit on 2026-08-25 and checked against
the tree.

**What this spec is for, in one sentence.** A person with Docker and one API key
runs one command and watches an agent write code and a gate judge it.

## Requirements, numbered here

`spec.md`'s Requirements section says "numbered at refinement". These are those
numbers. They live in this document because `plan.md` is one of the three files
assembled into every attempt prompt, so they reach the implementer intact.

**US1 — the gateway has a bundled half**

- **FR-001**: The install interview MUST ask `gateway mode (external|managed)`,
  using the same grammar and helper shape as `_ask_temporal`
  (`factory/cli/install.py:1764-1782`). Both answers MUST be accepted.
- **FR-002**: `mode = "external"` MUST preserve today's behaviour exactly —
  operator-supplied `base_url` and `master_key_env`, and every existing LLM
  verification test passing **unmodified**.
- **FR-003**: `mode = "managed"` MUST record the bundled gateway's address and
  that the compose project owns its lifecycle. It MUST NOT attempt to start
  anything: this story configures, the project runs.
- **FR-004**: `--from-file` (`install.py:1221 _install_from_file`) MUST accept
  the new key, so the demo selects managed mode with no interview. Add the key
  to `docs/ergane-install-answer.example.toml`, whose `[llm]` block is the
  documented shape.
- **FR-005**: The key-management capability probe (`verify.py:453-511` — mint a
  short-TTL key, assert it is model-constrained, read spend logs, revoke in a
  `finally`) MUST run identically for both modes. A managed gateway earns its
  green the same way an external one does.
- **FR-006**: `verify.py:415`'s invariant MUST hold: `gateway` remains the only
  mode a parsed config can carry. This story adds a mode to the *gateway*, not a
  third `llm.mode`. Do not touch that assertion.

**US2 — the demo project exists and is one file**

- **FR-007**: Add `container/compose.demo.yaml` declaring exactly three
  services: the engine, a LiteLLM gateway, and a Postgres for key management.
  The engine's image reference MUST derive from the same version source
  `container/compose.reference.yaml:10` uses.
- **FR-008**: Every volume MUST be a **named volume**. **No** mount pair may be
  same-path. This is the deliberate inverse of `_check_paths`
  (`container_project.py:318-329`) and the drift test MUST assert it *and* carry
  the reason in its failure message. See T1.
- **FR-009**: Exactly **one** environment variable may be mandatory — the
  upstream model credential. Every other value MUST carry a working default in
  the file. The drift test MUST fail if a second mandatory variable appears.
- **FR-010**: The project MUST ship a bundled answers file consumed via
  `--from-file`, and a registry whose aliases carry **no** `example/` prefix
  (`factory/config.py:57 EXAMPLE_ALIAS_PREFIXES`). The refusal at
  `verify.py:441` MUST NOT be weakened, relaxed or special-cased — the demo
  satisfies it. See T2.
- **FR-011**: The file MUST open with a header comment stating that it is a
  demonstration with volume-local state, that it does not land, and that
  `ergane install --engine=container` generates the operational project instead.
  Asserted by the drift test, in the manner `test-release.yml`'s credential
  comment is asserted by 108's FR-010.

**US3 — the epic halts at PASSED**

- **FR-012**: A halting mode MUST exist on the workgraph dispatch path such that
  a node reaching `PASSED` (`factory/workgraph/models.py:114-118`) is terminal
  and the landing phase never begins.
- **FR-013**: In that mode **no forge call may be made**. The committed test
  MUST fail the run if the forge seam is touched at all — a spy, not an
  inspection of the result.
- **FR-014**: The run's output MUST state that landing was **not attempted** and
  what would be required to land. An absent landing must never read as a failed
  one.
- **FR-015**: With the mode off, behaviour MUST be exactly today's through
  `MERGED`, proven by the existing workgraph tests passing unmodified.
- **FR-016**: In the halting mode, a node that **fails** its gate or judge MUST
  report failure as it does today. The mode changes where success stops, never
  what failure means.

**US4 — the file has a URL**

- **FR-017**: `.github/workflows/release.yml` MUST publish
  `container/compose.demo.yaml` as a release asset, in a step ordered **after**
  the image job. A compose file naming an image that does not exist yet is
  failure mode 13 in a new costume.
- **FR-018**: The workflow MUST assert that the published file's engine image
  tag equals the tag being released, and MUST fail the release on mismatch. Not
  a human comparison.
- **FR-019**: Every test 105 and 108 landed MUST pass **unmodified** — the
  preflight ordering (`release.yml:21,42-43`), the image job's `needs:`
  (`:98-99`), and the package linkage and visibility assertions.

## What already exists, and where

Read these before writing anything. All line numbers are from `5918ea5`.

**`factory/cli/install.py`**
- `:1764-1782` `_ask_temporal` — **the pattern FR-001 mirrors**. Note it raises
  `OperatorError` when `managed` is chosen without a systemd user session; the
  gateway's managed mode has no such host dependency and must not copy that
  guard.
- `:1221` `_install_from_file` — the non-interactive path FR-004 extends
- `:826-827`, `:848-858` the `--from-file` / `--non-interactive` flag wiring
- `:900-901` where `--from-file` short-circuits the interview

**`factory/controlplane/verify.py`**
- `:412-420` the LLM check's `gather`, carrying `# gateway is the only mode a
  parsed config can carry (048-US2)` and its `assert` — **FR-006 protects this**
- `:441` `if all(is_example_alias(alias) for alias in alias_to_personas)` — the
  refusal FR-010 satisfies rather than weakens
- `:453-511` the key-management probe — mint, constrain, spend logs, revoke in a
  `finally` so a key is never leaked on the failure path

**`factory/config.py`**
- `:57` `EXAMPLE_ALIAS_PREFIXES = ("example/",)`
- `:76` `is_example_alias`
- `:60` `shipped_registry_text`

**`factory/supervision/container_project.py`**
- `:318-329` `_check_paths` — raises when `mount.source != mount.target`, with
  the reason: "git records absolute paths in its worktree files, and a rewritten
  one breaks on the other side". **FR-008 is the deliberate inverse of this and
  must not change it.**
- `:452` `reference_project`, `:536` `resolve_project`, `:677` `render_compose`
- `:134-139` `ENGINE_TEMPORAL_ADDRESS`, `TEMPORAL_DB_NAME`

**`container/compose.reference.yaml`** — 56 lines. `:10` the image reference
whose version source FR-007 reuses; `:19-29` the same-path mount comments.

**`factory/supervision/container_supervisor.py`**
- `:39-43` `_CHILDREN` — the three supervised children. **The gateway does not
  join this dict** (see T3).

**`factory/workgraph/models.py`**
- `:74` `class NodeState`, `:78` the documented order
  `PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED → PR_OPEN → ENQUEUED → MERGED`
- `:86-87` records that `PR_OPEN`/`ENQUEUED` are "the landing phase's states"
  and `MERGED` the terminal — **this is the seam US3 uses**

**`factory/mergequeue/forge.py`**
- `:178` the `Forge` Protocol, eight methods. US3 must ensure none is called;
  this file is **not** edited by any story here.

**`.github/workflows/release.yml`** — `:21` `build-image-preflight`, `:42-43`
`build-and-publish` with its `needs:`, `:98-99` `build-and-publish-image`.

## Technical approach, story by story

### US1 — the gateway has a bundled half

One question, mirroring `_ask_temporal`. The shape of the config it writes
matters more than the prompt: `mode = "managed"` records an address the compose
project will serve at and a flag that the project owns the lifecycle. Nothing in
this story starts a process.

The temptation to resist is making managed mode *imply* anything about
verification. FR-005 exists because "it is ours, so it is fine" is how a probe
stops measuring. The key-mint round trip runs either way.

### US2 — the demo project exists and is one file

Three services. The gateway needs a model config; Postgres needs nothing beyond
a volume and a password with a baked default (this is a local demo database, not
a secret — say so in a comment so nobody files it as a leak).

**The volumes are the interesting part.** The operational project's mounts are
same-path because a host CLI and the container share git worktrees. The demo has
no host side: the sample repo, the state root and the Temporal database all live
in named volumes. Write the drift test to assert *not*-same-path and put the
reason in the assertion message, because the next person to read that file will
have read `container_project.py:326` first and will otherwise "fix" it.

### US3 — the epic halts at PASSED

The state machine already stops here; `PASSED` is a real state with the landing
phase after it. The work is a mode that makes it terminal and a statement that
says so.

FR-013 wants a **spy**, not an assertion about outcomes. A test that checks "no
PR was opened" passes when the forge was called and failed. Inject a forge whose
every method raises, and assert the run completes.

FR-014's wording is the story's whole value. "Landing not attempted" and
"landing failed" are different facts and the second is what a reader will
assume, because every other run they have seen lands.

### US4 — the file has a URL

One step in an existing job, ordered after the image. FR-018 wants the check
inside the workflow: read the published file back, extract the engine tag,
compare to `GITHUB_REF_NAME` minus `v`, exit non-zero on mismatch. The image job
already models this — it reads its own manifest back with `imagetools inspect`
rather than trusting the push.

## Traps

**T1 — you are about to write a mount the generator would refuse, and that is
correct.** `container_project.py:318-329` raises `OperatorError` for any bind
where source and target differ. The demo project's volumes deliberately violate
that shape, because the invariant protects a host CLI sharing git worktrees with
a container and the demo has no host side. **Do not "fix" the demo to be
same-path, and do not relax `_check_paths` to admit the demo.** They are two
artifacts with two jobs. The drift test must state this in its failure message.

**T2 — the `example/` refusal is not in your way, it is your specification.**
`verify.py:441` refuses a registry whose aliases are all `example/`-prefixed, and
`EXAMPLE_ALIAS_PREFIXES` is at `factory/config.py:57`. The demo satisfies this by
shipping real aliases the bundled gateway serves. **Do not add a bypass flag, do
not special-case a demo path, do not extend the prefix list.** A demo that turns
off the check that says "this is not configured" is demonstrating the wrong
product.

**T3 — the gateway is not a fourth supervised child.** `_CHILDREN`
(`container_supervisor.py:39-43`) has three entries and adding a fourth is
mechanically trivial. It is still wrong here, and the reason is Postgres: LiteLLM
key management needs a `DATABASE_URL`, so a bundled gateway drags a database into
the engine's PID namespace and restart policy, and every `ergane engine upgrade`
becomes a migration. 105 built upgrade as a drain-first verb because the engine
holds state. Compose siblings, ruled at drafting.

**T4 — `_ask_temporal` raises on a host with no systemd user session; do not
copy that guard.** `install.py:1775-1781` refuses `temporal.mode = "managed"`
when `systemctl --user` is unavailable, because the *native* tier supervises the
server through systemd. The gateway's managed mode is a compose service and has
no such host dependency. Copying the guard would refuse the demo on exactly the
machines it is for.

**T5 — one mandatory environment variable, and the test must be able to count.**
FR-009 is easy to satisfy today and easy to erode later. Write the drift test so
it *enumerates* what the file requires without a default and asserts the count,
rather than checking that one specific name is present.

**T6 — the demo database password is not a secret and a reviewer will think it
is.** A local Postgres reachable only on the compose network, holding LiteLLM key
metadata for a throwaway demo, has a baked default password. Put a comment on the
line saying so. Without it, the next audit files a finding and the next agent
"fixes" it into a required environment variable, breaking FR-009.

**T7 — US3's spy must fail the run, not record a failure.** A forge double whose
methods return sentinel values lets a call through and passes. Every method must
raise. The assertion is that the run completed, which is only possible if nothing
called it.

**T8 — do not implement a forge.** The eight-method Protocol at
`factory/mergequeue/forge.py:178` is a tempting way to "finish" the demo. The
operator ruled against it explicitly on 2026-08-25: a forge that merges without a
queue or required checks demonstrates `git merge`, not a factory. If a story here
seems to need one, the story is wrong, not the ruling.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
  depends_on: []
US2:
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011]
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: [FR-012, FR-013, FR-014, FR-015, FR-016]
  depends_on: []
  concurrent_with: [US1, US2]
US4:
  implements: [FR-017, FR-018, FR-019]
  depends_on: []
  depends_on_merged: [US2]
```

Chain depth 3 — US1 → US2 → US4 is the critical path, with US3 alongside from
round one.

## Sizing

Four stories. US2 is the largest and is mostly YAML plus a drift test. US1 is one
interview question and a config field, following a pattern already in the file.
US3 is a mode flag, a terminal-state change and an output sentence. US4 is one
workflow step and one assertion.

**US2 is the one at risk of sprawl.** Its unit of value is "the file exists,
comes up, and verifies" — not "the demo is delightful". Resist adding a seeded
sample repo with an interesting story, a web UI, or a tour. Those are separate
specs if they are anything.

## File contention

| story | owns |
| --- | --- |
| US1 | `factory/cli/install.py`, `factory/controlplane/config.py`, `docs/ergane-install-answer.example.toml`, its tests |
| US2 | `container/compose.demo.yaml` (new), the bundled answers file and demo registry (new), its tests |
| US3 | `factory/workgraph/` workflow and models, its tests |
| US4 | `.github/workflows/release.yml`, `tests/test_release_path.py` |

The sets are disjoint. US3 reads US2's file path in prose only, which is why
`concurrent_with` is declared.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch.** The committed `workgraph.json` is a
  compile-time snapshot carrying the absolute paths of the worktree it was
  compiled in. Re-derive with `--target-repo "$PWD"` from the operator checkout.
- **Do not run `scripts/gate-commit` while an attempt is in flight.** It creates
  `/tmp/ergane-gate-XXXXXX/specs`, and
  `tests/test_ergane_install_closing_step.py:450` asserts no `/tmp/ergane-*`
  directory contains `specs/`. A concurrent operator gate turns a **node's** gate
  red for a reason the node cannot see or fix. Measured twice on 2026-08-25.
- **US4 writes `.github/workflows/`.** 108/US1 proved the factory can push that
  directory over SSH, so the old scope refusal should not recur — but US4 is
  isolated at the end of the chain so a recurrence kills only it.

## Verification the operator will run, independent of the gate

```bash
export ANTHROPIC_API_KEY=…
curl -fsSL https://github.com/bryantharpeorg/ergane/releases/latest/download/compose.yaml \
  | docker compose -f - up
```

On a machine that has never had Ergane installed. The stack comes up, one story
is dispatched, an agent writes code, a gate runs, a judge renders a verdict, and
the output states that landing was not attempted.

**Run it on the x86 rig, not the factory host.** The factory host has a config, a
registry, a state root and a running worker, and any of them can make a broken
demo look like a working one.
