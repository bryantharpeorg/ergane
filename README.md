# Ergane

Ergane is an agentic software factory. It turns Spec Kit feature specs into
merged, verified code by dispatching headless coding agents through an
orchestrated DAG, with attributed per-node spend, mechanical acceptance-criteria
verification, and merge-queue discipline.

This page takes a new operator from a bare machine to a dispatched epic. Every
command below is real; run them in order.

## What you must already have

- A LiteLLM-shaped gateway. Ergane dispatches through a LiteLLM proxy that
  mints per-node virtual keys; standing one up is outside what Ergane does.
  The control plane will refuse `llm.mode = "direct"` with the same wording
  the parser uses: every attempt runs on its own model-constrained, TTL'd
  virtual key minted at the LiteLLM proxy, and a per-persona provider endpoint
  has no such key to mint, revoke or attribute. Put a LiteLLM-shaped gateway in
  front of the provider and declare `llm.mode = "gateway"`.
- An authenticated `gh` CLI, able to push to and administer the repositories you
  want Ergane to target.
- `bwrap` on `PATH`, used by the default runtime to sandbox agent work.
- `git` and `uv`.
- Python 3.11 or newer.
- A Node.js runtime, used by the agent CLI.
- A systemd user session, if you want `ergane worker install` to run managed
  units under your user manager.

See `factory/controlplane/config.py` for the exact control-plane schema, and
`factory.yaml` for the gate and loop composition this repository declares.

## Getting the source

```bash
git clone <this-repository>
cd ergane
```

## Installing Ergane

Run the control-plane interview and verify what it writes. The interview asks
for environment variable names, not values; set those variables in your shell
before running the commands that need them (`scripts/ergane-env.sh` is one
operator-specific way to do that).

```bash
uv venv
uv pip install -e .
ergane install
```

Re-run the verification without the interview when you change the environment:

```bash
ergane install --verify
```

## Installing the worker

Run the worker and operator bridge under systemd user supervision:

```bash
ergane worker install
```

## Joining a repository

Join a git repository so Ergane can dispatch against it:

```bash
ergane init
```

To also wire the repository's GitHub side, run:

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

For the current state of every spec, run `ergane spec list specs`. For what an
epic is doing right now, run `ergane build status <epic-id>`. For open defects,
run `ergane findings list`.

## Leaving

To remove a repository from the engine without touching its files:

```bash
nergane repo forget <repo-slug>
```

To remove the worker units:

```bash
nergane worker uninstall
```

## Where the binding documents live

- `.specify/memory/constitution.md` — the standards every node obeys.
- `docs/architecture.md` — how the factory works.
- `docs/decisions.md` — the immutable decision log.
- `CONTEXT.md` — the vocabulary this repository uses.
- `scripts/ergane-env.sh` — the shell environment the CLI commands expect.
