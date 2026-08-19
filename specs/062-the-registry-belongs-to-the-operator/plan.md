# Implementation Plan: the registry belongs to the operator

**Spec**: `specs/062-the-registry-belongs-to-the-operator/spec.md`

## What already exists, and where

- `factory/config.py:38–52` — `REGISTRY_FILENAME` and
  `_resolve_default_registry_path()`. Read the docstring before changing
  anything: it explains that package-data resolution exists because an installed
  wheel has no repo above it. That reasoning is correct and survives this spec.
  This function becomes the *last* branch of a longer chain, not a thing to
  delete.
- `factory/config.py:212` — where `skills` is parsed and validated.
- `factory/controlplane/config.py:202` — **the pattern to copy.** "Return the
  config path: env override, then `XDG_CONFIG_HOME`, then `HOME`."
  `ERGANE_CONFIG_PATH` wins, legacy `FACTORY_CONFIG_PATH` is honoured. Mirror
  this shape, including the legacy-name courtesy if a legacy name exists.
- `factory/controlplane/config.py:53` — `DEFAULT_CONFIG_REL`, the relative-path
  constant. The registry needs its sibling.
- The five bare call sites US1-S5 must reach:
  `factory/activities/roadmap_activities.py:334`,
  `factory/cli/nouns/spec.py:408`, `factory/workgraph/cli.py:100`,
  `factory/activities/agent_activities.py:260` and `:331`.
- The three `skills=()` construction sites: `factory/workgraph/cli.py:584`,
  `factory/cli/nouns/build.py:234`, `factory/cli/nouns/spec.py:61`.
- `factory/workgraph/adapter.py:339` — where the node's factory-owned HOME is
  set. This is the anchor for US3-S2's documentation claim; read it and describe
  what it actually does rather than paraphrasing this plan.
- `pyproject.toml` — the force-include that copies the repo-root `personas.yaml`
  to `factory/personas.yaml` at build time. US2 changes *what* is shipped, so
  check whether the force-include still points at the right source file.

## Traps

**1. The packaged path is not a fallback for a failed override.** FR-003. If
`$ERGANE_PERSONAS_PATH` names a file that does not parse, failing over to package
data means the operator edits a file, sees no change, and debugs their gateway.
Present-but-broken fails; absent moves to the next layer. Those are different.

**2. Do not read the registry by repo-root path.** 054's trap 4, still live. It
works in a checkout and fails in the installed package, and this repository has
already had to prove a defect was *not* a packaging fault by running both. The
last branch of your chain is `importlib.resources`, unchanged.

**3. Five call sites bypass the seam today; a sixth will be added while you
work.** US1-S5 asserts the override changes what each of the five resolves.
Consider making the bare `load_personas()` call the resolver internally rather
than requiring every caller to remember — a seam callers must opt into is a seam
that decays. Whatever you choose, the test asserts behaviour at the call sites,
not at the resolver.

**4. This spec can break the factory that is building it.** US2-S6 exists for
exactly that. This repository's own `personas.yaml` sits at the repo root and its
epics dispatch against it. If your precedence chain resolves an operator's
`~/.config/ergane/personas.yaml` ahead of the checkout's, work inside this
repository silently starts using the wrong registry. Decide what a checkout does,
state it, and test it — before you run anything that dispatches.

**5. Do not modify factory code while an attempt is in flight.** The worker
imports it live, and `factory/config.py` is imported by activities. This is not a
theoretical concern for this spec specifically.

**6. `--verify`'s failure message is the operator-facing half of US2.** FR-008.
Five unknown aliases reported as five gateway faults sends the operator to debug
their proxy. One condition naming the registry sends them to the file they need
to edit. The information is identical; the routing is not.

**7. US3 has two acceptable answers and one unacceptable one.** Wire `skills`
into the adapter invocation, or document it as reserved. What is forbidden is
leaving the field parsed, validated, undocumented and dead. Pick, and hold the
pick with a test that would fail if it silently reverted.

**8. The skill-scope documentation must be checked against the adapter, not
against this plan.** US3-S2 claims home-scoped skills are invisible and
project-scoped committed skills are visible. That is the reporter's observation
and it is consistent with `factory/workgraph/adapter.py:339`, but you are
writing it into the tree as fact. Verify it against the adapter's actual HOME and
worktree handling first.

**9. The judge sees the diff and the criteria. Nothing else.** SC-001 spans an
upgrade cycle and is runtime evidence — **paste the transcript into the diff.**

**10. Story edges.** US1 and US2 both edit `factory/config.py` and are
serialised. US3 is independent of both.

## Sizing

Three stories. US1 is a resolver mirroring one that already exists, plus routing
five call sites through it — small, but the call-site sweep is where an
implementer under-delivers, so US1-S5 is written to catch that. US2 is a rewrite
of the shipped YAML plus a seeding step in install plus the `--verify` message.
US3 is either a small wiring change or a documentation change plus its test.

Trap 4 is the one that decides whether this epic is safe to run in this
repository. Resolve it before dispatch, not during.

## Verification the operator will run, independent of the gate

- **Prove US1 by mutation.** Put a registry at `~/.config/ergane/personas.yaml`
  with one persona pointed at a deliberately wrong alias, run `ergane install
  --verify`, and confirm the failure names *that* alias. If it names a packaged
  alias instead, the override is not reaching the probe.
- **Prove US2 across an upgrade.** SC-001. Install from PyPI, edit the seeded
  registry, run `uv tool upgrade ergane-cli`, and confirm the edits survive. This
  is the whole point of the spec and it cannot be proven by any unit test.
- **Prove US2-S6 by dispatch.** Run an epic in this repository after the change
  and confirm it resolves this repository's registry. Do this before believing
  the epic is done.
- **Read the shipped example as a stranger.** Open the packaged `personas.yaml`
  and ask whether someone who has never met this project could fill it in. That
  is SC-002 and no test measures it.
