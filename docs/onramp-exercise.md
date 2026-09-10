# The on-ramp exercise: what it does, what it costs, when to run it

`tests/test_live_onramp.py` drives Ergane's whole on-ramp against a scratch
repository — `ergane install` → `ergane init --wire` → `ergane repo onboard` →
one dispatched epic → a pull request read back from GitHub and asserted
`MERGED`. It is 061's US4 (FR-011, FR-012).

Read this before running it: it creates a real GitHub repository, spends real
model budget and takes real minutes, and discovering that by running it is the
cost this page exists to avoid.

It exists because three readiness checks each reported green on a machine that
could not dispatch, could not land, and died on its first roadmap tick. Each was
honest; nothing measured the composition, so nothing was red.

## Prerequisites

It **skips** rather than fails when any of these is absent, naming the one that
is missing. `-m live_onramp` selects it; the marker does not guard it, because
nothing passes `-m` in CI or in this repository's gate.

- **`ERGANE_ONRAMP_ORG`** — a GitHub *organization* the run may create and
  delete a repository in. Not a preference: 059's rule requires it, because a
  user-owned repository cannot carry the merge-queue ruleset.
- **`gh` on `PATH`, authenticated** — `gh auth login`, with rights to create and
  delete repositories in that organization and configure rulesets.
- **`claude` on `PATH`** — the current exercise's hard-coded collection guard.
  This `claude` prerequisite is not the runtime runner selection: the dispatched
  persona is resolved from the copied persona registry. If that persona uses
  Codex, its actual CLI, provider, sandbox and tool configuration must also work.
  Passing this guard is not a Codex-specific qualification or a check of every
  supported runner. See [Codex gateway setup](codex-gateway-setup.md).
- **`LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY`** — a LiteLLM proxy *with key
  management enabled* (started with a `DATABASE_URL`). A config-only proxy stops
  the run at the install stage, which is 061/US1 working.
- **A Temporal server** — reachable at `TEMPORAL_ADDRESS` in
  `TEMPORAL_NAMESPACE` (defaults `127.0.0.1:7233` / `ergane`).
- **A persona registry naming real aliases** — the shipped one carries
  `CHANGEME`. The run copies yours into its workspace rather than editing it.

Use a dedicated test namespace and a deliberately selected gateway registry.
The exercise talks to the declared external services even though its queue and
local workspace are run-scoped. It does not provision every missing service or
prove that the current worker deployment and a packaged release match.

`ERGANE_ONRAMP_TIMEOUT_S` sets the node's attempt deadline (default 1200s).
Review the source and scratch organization before exporting the opt-in variable;
it authorizes creation and deletion of a public scratch repository.

```bash
eval "$(scripts/ergane-env.sh)"
export ERGANE_ONRAMP_ORG=<your-scratch-org>
uv run pytest tests/test_live_onramp.py -q -s
```

`-s` is worth having: a failure names its stage — `on-ramp exercise failed at
stage 'onboard': …` — and the transcripts are the diagnostic.

## What it costs

**15–40 minutes**, most of it the agent attempt and the merge queue's Actions
runs. **One implementer attempt plus one judge scoring** on a one-file story, at
your gateway's rates: the ladder is capped at one attempt with no debugger
cycle, because a broken composition should report in minutes rather than spend
three attempts discovering the same thing. **One public GitHub repository**
created and deleted, one pull request, and the Actions minutes for its required
check on both `pull_request` and `merge_group`. **One Temporal workflow**, one
worker on a run-scoped queue, and virtual keys minted and revoked per attempt.

Cleanup attempts to delete the scratch repository and remove its temporary
root on both success and failure; a cleanup error is reported, not a guarantee
that every artifact is gone. Gateway usage, GitHub audit/Actions records and
Temporal history remain external effects. Every local path the run resolves — config, registry, runtime root,
ledger, evidence store — derives from a `tmp_path` it was handed, with `HOME`,
both XDG variables and every `ERGANE_*`/`FACTORY_*` path variable relocated
beneath it. Cleanup deletes the exact slug `gh repo create` answered for, and
removes a tree only when it is under the temporary directory *and* named the way
this exercise names its roots — either alone is a convention, not a boundary for
an act that deletes. And no Temporal schedule is created: `ergane init` tries,
D-045's guards refuse under `PYTEST_CURRENT_TEST`, and the run asserts that.

## When to run it

Before promoting a buildout branch to `main`; after any change to `ergane
install`, `ergane init`, `ergane repo onboard`, the forge wiring or the
merge-queue landing path; after changing the persona registry or the gateway.
Not on every commit — it is a composition check, not a gate, and the gate runs
the simulated half (`tests/test_onramp_exercise.py`) instead.

## The SC-005 drill: proving the exercise still measures something

An end-to-end test nobody has watched fail is an end-to-end test nobody has
tested. Revert each of 061's three repairs in turn, run the exercise, confirm it
goes red, then restore it.

**US1** — revert `LLMProbe` minting a key, against a config-only LiteLLM (no
`DATABASE_URL`, SC-001's second proxy): the exercise fails at stage `install`.
With key management reverted the verification passes and the epic dies
mid-dispatch instead, which is the failure this repair turns into a fast local
check. **US2** — revert `ergane init` creating `specs/`: stage `init`, which
checks the directory exists, because a schedule polling a directory that does
not exist is a four-tick outage in a journal nobody reads. **US3** — revert the
gate placeholder: stage `init` again, which loads the written manifest and
refuses any gate command `factory/mergequeue/onboard.py` calls a no-op.

If a revert does *not* turn it red, the exercise is not measuring the
composition and the gap is the thing to fix — not the drill.
