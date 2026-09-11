# Operator setup

This guide covers the gateway-backed setup path, from prerequisites to a dispatched
epic. For the system overview and a first supervised trial, start with the
[README](../README.md). The [installation reference](cli/install.md) covers the
available model routes and engine deployment choices.

For Codex CLI builders using Ollama Cloud through that gateway, follow the
[Codex gateway setup](codex-gateway-setup.md) alongside this guide. Selecting
Codex as a builder does not change the provider used by your operator session
or the independent judge.

Paths in commands and code spans below are relative to the repository root unless
shown as absolute paths. Choose the installation and deployment path that fits
your environment before running its commands.

The same path is also set as a single illustrated page — the supervised demo
with the ladder it climbs, the six steps, and the trap each one hides — at
[`docs/onramp.html`](onramp.html). Open it in a browser rather than on
GitHub, which renders it as markup. It is the shorter read; this page is the
fuller one.

## What you must already have

### A LiteLLM gateway, backed by a database

In gateway mode, Ergane dispatches through a LiteLLM proxy. This prerequisite most
often looks satisfied when it is not, so it is worth stating exactly.

**The proxy must be database-backed.** Every attempt runs on its own
model-constrained, TTL'd virtual key: Ergane mints one with `POST /key/generate`,
reads what it spent through `GET /key/info` and `GET /spend/logs/v2`, and revokes
it when the attempt ends. Those endpoints exist only when LiteLLM has a
`DATABASE_URL`. A config-only proxy answers `GET /v1/models` and
`POST /v1/chat/completions` perfectly and returns 404 for all of the rest — so it
passes a casual smoke test and then fails at the first dispatch.

**The proxy must serve every gateway-routed alias the persona registry names.**
That includes each `model` and non-null `fallback` in the selected
`personas.yaml` for personas with `route: gateway`. Deterministic personas
(`agent: none`) need no model; subscription-routed personas use a different
credential path and do not turn their model names into gateway aliases. Run
`ergane install --requirements` to print the exact set for your registry, or
`ergane install --scan` to see what a candidate endpoint actually offers before
you commit to it.

`llm.mode` takes `gateway` or `direct`, and the control plane accepts either. It
names what `direct` costs at the moment you choose it: the declared key is handed
to every attempt unexpiring, the registry's model bindings become a hint rather
than a gate, and spend attribution goes away entirely, because there is no proxy
to read per-key spend from. Two of those three are security properties rather
than bookkeeping. Put a LiteLLM-shaped gateway in front of the provider and
declare `llm.mode = "gateway"` unless you have decided to give them up.

### Everything else

- An authenticated `gh` CLI, able to push to and administer the repositories you
  want Ergane to target.
- **A GitHub merge queue you are allowed to enable.** Merge queues are available
  on public repositories owned by an organization, and on private repositories
  only under GitHub Enterprise Cloud. A user-owned repository cannot host one at
  any plan level, so make the target repository organization-owned before you
  wire it.
- **A prepared Spec Kit trio.** Each numbered feature directory under `specs/`
  holds its spec, plan and tasks files. You can author those documents directly
  from the committed `.specify/templates/`; Ergane does not require an authoring
  skill to be installed before it can parse them. Optional
  [Spec Kit](https://github.com/github/spec-kit) helpers belong to your chosen
  authoring client and need that client's installation instructions. This
  repository's templates, shell scripts and standards at
  `.specify/memory/constitution.md` are already committed.
- `bwrap` on `PATH`, used by the default runtime to sandbox agent work.
- `git` and `uv`.
- Python 3.11 or newer.
- The selected agent CLI on the worker host, plus the target's toolchain.
  Ergane's current sandbox toolchain also expects Node.js; a standalone Codex
  executable does not by itself remove that requirement.
- A systemd user session, if you want `ergane worker install` to run managed
  units under your user manager.

See `factory/controlplane/config.py` for the exact control-plane schema, and
`ergane.yaml` for the gate and loop composition this repository declares.
The legacy name `factory.yaml` remains compatibility context; use the manifest
actually selected for your target.

On Ubuntu 23.10 and later, `kernel.apparmor_restrict_unprivileged_userns=1`
denies user namespaces by default. The `apparmor=unconfined` option on the
demo container does not lift it: AppArmor attaches a profile by executable
path on exec, so `bwrap` inside the container is mediated by the *host's*
policy. The profile this repository ships grants `/usr/bin/bwrap` the
`userns` permission. Load it once from a checkout:

```bash
printf '%s\n' \
  'abi <abi/4.0>,' \
  'include <tunables/global>' \
  'profile bwrap /usr/bin/bwrap flags=(unconfined) {' \
  '  userns,' \
  '  include if exists <local/bwrap>' \
  '}' | sudo tee /etc/apparmor.d/bwrap
sudo apparmor_parser -r /etc/apparmor.d/bwrap
```

The profile is at `container/ergane-bwrap.apparmor` and is not installed by any
package; running the two commands above is the operator's deliberate act.

## Installing Ergane

There are two install paths and they are not interchangeable. Pick by what you
intend to do.

### To run Ergane against your own repositories

Install the published distribution. The PyPI name is `ergane-cli`; the command it
puts on your `PATH` is `ergane`.

```bash
uv tool install ergane-cli
```

### To work on Ergane itself

Install from a checkout, in editable mode.

```bash
git clone https://github.com/bryantharpeorg/ergane.git
cd ergane
uv venv
uv pip install -e .
```

### The difference that will bite you

The two install paths have different final registry fallbacks, but explicit
configuration wins over both. Resolution order is:

1. `ERGANE_PERSONAS_PATH` (or the legacy `FACTORY_PERSONAS_PATH`).
2. The operator registry under the XDG config directory, normally
   `/home/<operator>/.config/ergane/personas.yaml` on Linux (a host path,
   not a file inside the repository).
3. Packaged persona data, or the checkout's root `personas.yaml` when running
   from source without packaged data.

Initial registry seeding preserves an existing file; the interactive interview
can update model choices you deliberately confirm. Replace placeholder model and fallback aliases
with aliases your gateway serves. Editing a file in the current directory does
not select it, and even an editable checkout can be overridden by an existing
operator registry. `ergane install` reports the resolved registry path;
`ergane env --sources` helps identify environment overrides.

For a source checkout that should use its own registry, declare that choice
explicitly in the environment used by both the CLI and the worker. Registry
changes affect future dispatch configuration, not an already frozen epic;
never edit a running node's copied configuration to switch its route.

## Configuring the control plane

Run the interview and let it write the control-plane config. The interview asks
for environment **variable names**, not values; set those variables in your shell
before running the commands that need them.

```bash
ergane install
```

`scripts/ergane-env.sh` is one operator-specific way to set them, and it is the
way this repository does it. It **prints** `export` lines rather than setting
them, so eval it — sourcing it appears to work and sets nothing:

```bash
eval "$(scripts/ergane-env.sh)"
```

Re-run the verification without the interview whenever the environment changes:

```bash
ergane install --verify
```

If you do not yet know what to point it at, discover first — this writes nothing:

```bash
ergane install --scan
```

## Installing the worker

For native versioned workers, use an Ergane source checkout: the deploy command
needs a Git commit to freeze, not only an installed wheel. A package-only
installation can use the [container engine](container.md), with the engine
image matching the CLI version.

Put the bridge and probe under systemd user supervision, then put a worker
version on the floor. Install writes a *versioned* unit template rather than a
worker; `deploy` freezes a commit into a checkout of its own and starts an
instance serving it, so every epic finishes on the code it started with.

```bash
ergane worker install
ergane worker deploy <validated-commit-or-tag>
```

On a host installed before versioning, `ergane worker migrate` retires the old
`ergane-worker.service` — refused while any pre-versioning epic is still open.

## Joining a repository

Join a git repository so Ergane can dispatch against it. `ergane init` resolves
upward to the nearest enclosing repository, which is not always the one you
meant — so when the directory you run it in is not itself the repository root,
it names the root it resolved and asks before enrolling anything. Answer `y` to
proceed, or name the repository outright:

```bash
ergane init
ergane init <repository-root>
```

Under `--non-interactive` there is nobody to ask, so a resolved root that
differs from the invocation directory is refused rather than assumed.

Judge a repository's readiness without writing anything:

```bash
ergane init --check
```

To also wire the repository's GitHub side — enable the merge queue on the
declared landing branch, require one check per declared gate, and scaffold the
workflow that produces them:

```bash
ergane init --wire
```

## Onboarding a target repository

Register the repository with the engine:

```bash
ergane repo onboard <target-repo-path>
```

## Dispatching your first epic

For the first supervised trial, validate and dispatch a prepared spec trio:

```bash
ergane spec validate specs/001-example --target-repo "$PWD"
ergane build ship specs/001-example --target-repo "$PWD" --halt-after-pass
```

Replace the example directory with your own spec. `build ship` asks before
dispatch; `--halt-after-pass` stops passing work before landing, not before
agent execution or model cost. Both the target and specs paths must resolve
on the worker host. Review the attempt, gates and judge before authorizing
normal landing. The [build reference](cli/build.md) covers the full lifecycle.

If you already have a freshly derived, validated graph, start it directly:

```bash
ergane build start <workgraph.json>
```

Do not edit a compiled graph by hand or reuse one after changing its source
trio; derive it again through the supported spec commands.

## Asking the system about itself

Ergane answers questions about its own state, and those answers are live. Prefer
them to anything written down, including this page.

| Question | Command |
| --- | --- |
| What is the whole floor doing right now | `ergane status` |
| What state is every spec in, and what blocks each | `ergane spec list specs` |
| Which of a spec's stories are landed in git | `ergane spec landed <spec-dir>` |
| What is one epic doing right now | `ergane build status <epic-id>` |
| What defects are open | `ergane findings list` |
| What did the work cost | `ergane usage --by epic` |
| Is anything waiting on me | `ergane escalations list` |
| Is the installation healthy | `ergane doctor` |
| What operator skill files are present | `ergane skills status` |

`ergane skills status` reads the packaged resources, destination files and
ownership manifest. Its filesystem report does not establish that a fresh
Codex or Claude session loaded those skills. Skill installation and teardown
are separate changes to the operator's home.

`ergane spec landed <spec-dir>` scans the default branch unless told otherwise,
and a factory does not necessarily land there — pass `--default-branch` whenever
the answer matters.

## Leaving

Choose the scope of removal before changing the host. Preview the full-host
teardown with:

```bash
ergane uninstall --check
```

This read-only command reports the proposed steps without stopping services,
forgetting repositories or removing files. Review the
[uninstall reference](cli/uninstall.md), including evidence export and retained
configuration, before requesting the actual teardown. A preview is not a
verification that the removal preserves every filesystem layout.

To remove a repository from the engine without touching its files:

```bash
ergane repo forget <repo-slug>
```

To remove the worker units, exactly as `ergane worker install` wrote them:

```bash
ergane worker uninstall
```

Full-host uninstall also keeps the control-plane config and its secrets under
your XDG config directory, even with `--purge`. The manifest, gitignore entry
and runtime directory `ergane init` wrote into your repository remain repository
files. Removing either set is a separate, deliberate action.
Removing the package itself is your package manager's job — `uv tool uninstall
ergane-cli`.

## Where the binding documents live

- `.specify/memory/constitution.md` — the standards every node obeys.
- `docs/architecture.md` — how the factory works.
- `docs/cli/` — reference documentation for every `ergane` noun and verb.
- `docs/decisions.md` — the immutable decision log.
- `CONTEXT.md` — the vocabulary this repository uses.
- `scripts/ergane-env.sh` — the shell environment the CLI commands expect.
- `personas.yaml` — the personas, their models and their fallbacks.
- `ergane.yaml` — this repository's own manifest, as `ergane init` writes one.
