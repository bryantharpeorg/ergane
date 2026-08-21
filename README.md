# Ergane

Ergane is an agentic software factory. It turns Spec Kit feature specs into
merged, verified code by dispatching headless coding agents through an
orchestrated DAG, with attributed per-node spend, mechanical acceptance-criteria
verification, and merge-queue discipline.

This page takes a new operator from a bare machine to a dispatched epic. Every
command below is real; run them in order.

## What you must already have

### A LiteLLM gateway, backed by a database

Ergane dispatches through a LiteLLM proxy. This is the prerequisite that most
often looks satisfied when it is not, so it is worth stating exactly.

**The proxy must be database-backed.** Every attempt runs on its own
model-constrained, TTL'd virtual key: Ergane mints one with `POST /key/generate`,
reads what it spent through `GET /key/info` and `GET /spend/logs/v2`, and revokes
it when the attempt ends. Those endpoints exist only when LiteLLM has a
`DATABASE_URL`. A config-only proxy answers `GET /v1/models` and
`POST /v1/chat/completions` perfectly and returns 404 for all of the rest — so it
passes a casual smoke test and then fails at the first dispatch.

**The proxy must serve every model alias the persona registry names.** That is
every `model` and every `fallback` in `personas.yaml`, excluding personas
declared `agent: none`, which have no model by construction. Run
`ergane install --requirements` to print the exact set for your registry, or
`ergane install --scan` to see what a candidate endpoint actually offers before
you commit to it.

The control plane refuses `llm.mode = "direct"` for the same reason: a per-persona
provider endpoint has no key to mint, revoke or attribute. Put a LiteLLM-shaped
gateway in front of the provider and declare `llm.mode = "gateway"`.

### Everything else

- An authenticated `gh` CLI, able to push to and administer the repositories you
  want Ergane to target.
- **A GitHub merge queue you are allowed to enable.** Merge queues are available
  on public repositories owned by an organization, and on private repositories
  only under GitHub Enterprise Cloud. A user-owned repository cannot host one at
  any plan level, so make the target repository organization-owned before you
  wire it.
- `bwrap` on `PATH`, used by the default runtime to sandbox agent work.
- `git` and `uv`.
- Python 3.11 or newer.
- A Node.js runtime, used by the agent CLI.
- A systemd user session, if you want `ergane worker install` to run managed
  units under your user manager.

See `factory/controlplane/config.py` for the exact control-plane schema, and
`factory.yaml` for the gate and loop composition this repository declares.

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

The two paths resolve the persona registry from different places. An editable
checkout reads the `personas.yaml` at the root of that checkout, so editing it
takes effect immediately. A published install reads the copy packaged inside the
distribution — so editing a `personas.yaml` in some directory you happen to be
standing in changes nothing, and the file you want to edit is not obviously
anywhere.

If you installed the published package and want your own registry, put it where
the resolver looks rather than where you happen to be; `ergane install` reports
the path it resolved, and that path is the answer.

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

Run the worker and operator bridge under systemd user supervision:

```bash
ergane worker install
```

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

Start a compiled workgraph:

```bash
ergane build start <workgraph.json>
```

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
| What did the work cost | `ergane usage` |
| Is anything waiting on me | `ergane escalations list` |
| Is the installation healthy | `ergane doctor` |

`ergane spec landed` scans the default branch unless told otherwise, and a
factory does not necessarily land there — pass `--default-branch` whenever the
answer matters.

## Leaving

Ergane has an inverse for the two things it registers, and you should know which
two before you start.

To remove a repository from the engine without touching its files:

```bash
ergane repo forget <repo-slug>
```

To remove the worker units, exactly as `ergane worker install` wrote them:

```bash
ergane worker uninstall
```

Two things have no inverse verb today, and come off by hand: the control-plane
config the interview wrote under your XDG config directory, and the manifest,
gitignore entry and runtime directory `ergane init` wrote into your repository.
Removing the package itself is your package manager's job — `uv tool uninstall
ergane-cli`.

## Where the binding documents live

- `.specify/memory/constitution.md` — the standards every node obeys.
- `docs/architecture.md` — how the factory works.
- `docs/decisions.md` — the immutable decision log.
- `CONTEXT.md` — the vocabulary this repository uses.
- `scripts/ergane-env.sh` — the shell environment the CLI commands expect.
- `personas.yaml` — the personas, their models and their fallbacks.
- `ergane.yaml` — this repository's own manifest, as `ergane init` writes one.
