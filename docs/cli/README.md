# The `ergane` CLI

Reference documentation for every noun and verb the operator command exposes.
One page per noun, listed below.

This is **descriptive**. It says what the commands do and how they behave. It
binds nobody: `.specify/memory/constitution.md` is the normative document, and
`docs/architecture.md` describes the machinery these commands drive.

Verified against the shipped parser on 2026-09-01. Where this page and
`ergane <noun> --help` disagree, the parser is right — every flag below was read
out of it rather than transcribed.

## The shape of the command

```
ergane [--debug] [--version] <noun> [<verb>] [arguments]
```

There is no global config flag and no global dry-run flag. Nouns are discovered by
walking `factory/cli/nouns/`; there is no list of them anywhere else, which is
why a new noun appears in `ergane --help` the moment its module exists.

`--version` prints the version, the git revision, and the endpoints the CLI
would dial — **without dialing them**:

```
$ ergane --version
ergane 0.5.0 (3359a5a)
Temporal: localhost:7233 (namespace ergane)
Proxy: not configured
```

`--debug` prints full tracebacks for unexpected errors. Without it, an
unexpected error is rendered as one line.

## The nouns

Ordered as `ergane --help` orders them — setup first, daily work in the middle,
teardown at the end.

| noun | what it is for | page |
| --- | --- | --- |
| `install` | configure and verify the control plane | [install.md](install.md) |
| `worker` | supervise the worker and the operator bridge with systemd | [worker.md](worker.md) |
| `engine` | manage the engine container | [engine.md](engine.md) |
| `uninstall` | take Ergane off this host, in the order that is safe | [uninstall.md](uninstall.md) |
| `init` | join a git repository to Ergane | [init.md](init.md) |
| `spec` | list, validate, derive, scaffold and audit specs | [spec.md](spec.md) |
| `status` | what the whole floor is doing right now | [status.md](status.md) |
| `build` | start, watch and signal an epic | [build.md](build.md) |
| `escalations` | what is waiting on you | [escalations.md](escalations.md) |
| `answer` | answer an operator question by its correlation id | [answer.md](answer.md) |
| `doctor` | run all registered probes | [doctor.md](doctor.md) |
| `findings` | manage the findings ledger | [findings.md](findings.md) |
| `usage` | read-only usage rollups over the ledger | [usage.md](usage.md) |
| `repo` | manage target repositories | [repo.md](repo.md) |
| `roadmap` | run and steer the roadmap scheduler | [roadmap.md](roadmap.md) |
| `env` | show environment variables the CLI reads | [env.md](env.md) |
| `completion` | emit a shell completion script | [completion.md](completion.md) |

## By the question you are asking

| question | command |
| --- | --- |
| What is the floor doing? | `ergane status specs` |
| What is one epic doing? | `ergane build status <epic-id>` |
| Which of a spec's stories are actually in git? | `ergane spec landed <spec-dir>` |
| Is this spec fit to dispatch? | `ergane spec validate <spec-dir>` |
| Compile a spec into a work graph | `ergane spec derive <spec-dir>` |
| Validate, derive, review, then dispatch | `ergane build ship <spec-dir>` |
| What is waiting on me? | `ergane escalations list` |
| Answer a question an agent asked | `ergane build answer <epic-id>` |
| What defects are open? | `ergane findings list` |
| What did an epic cost? | `ergane usage --by epic` |
| Is my environment wired correctly? | `ergane env --sources`, `ergane install --verify` |
| Why did a node fail its verification? | `ergane build attempts <epic-id>` |
| An epic is gone and the work is not | `ergane build salvage <graph>` |

## Exit codes

The same boundary wraps every handler, so these mean the same thing under every
noun (`factory/cli/errors.py`).

| code | name | meaning |
| --- | --- | --- |
| 0 | `EXIT_OK` | the command answered |
| 1 | `EXIT_USER` | something the operator can fix without leaving the terminal — a refusal, a bad path, a spec that does not validate |
| 2 | `EXIT_USAGE` | argparse rejected the arguments |
| 3 | `EXIT_TRANSPORT` | a service the factory talks to did not answer — Temporal unreachable, the gateway down |
| 130 | `EXIT_INTERRUPT` | Ctrl-C |

The distinction between 1 and 3 is the one worth scripting against: **1 is your
problem, 3 is the plane's.** Retrying a 1 will fail identically; retrying a 3
often will not.

## Conventions that hold across nouns

**`--json` is a document, not a prettier table.** Where a verb offers it, the
JSON is the machine contract and the human view is rendered from the same data.
Script against the JSON.

**Read-only verbs say so.** `status`, `env`, `usage`, `findings list`,
`escalations list`, `build salvage`, `build attempts`, `repo list`, and
`--check` on `init`, `install` and `uninstall` write nothing, signal nothing,
and create nothing.

**`--target-repo` is a worker-host path, not a URL and not a remote.** Several
verbs require it because the compiled artifact records it and the worker
resolves it later on a possibly different machine.

**`--specs-root` defaults to `specs`.** It is relative to the process's working
directory unless given absolute.

**Locks are honest about waiting.** Verbs that write shared state
(`install`, `repo rebuild`, `repo forget`) take `--lock-timeout` seconds and
**refuse** rather than block forever.

## The environment

`ergane env` lists every variable the CLI reads, whether it is set, and which
source won. Secrets are redacted in the bare listing:

```
$ ergane env
TEMPORAL_ADDRESS= (default: localhost:7233)  [set, default]
TEMPORAL_NAMESPACE= (default: ergane)  [set, default]
LITELLM_PROXY_URL=  [set, override of the control-plane config]
LITELLM_MASTER_KEY=[REDACTED]  [set, override of the control-plane config]
TELEGRAM_BOT_TOKEN=[REDACTED]  [set, required]
ERGANE_LEDGER_PATH=  [not set, default .factory/ledger.db]
ERGANE_VERIFICATION_DB_PATH=  [not set, default .factory/verification.db]
```

Environment variables **override** the control-plane config at
`~/.config/ergane/config.toml`. `ergane env --sources` reports which source won
and names the route not taken, which is the fastest way to explain a CLI that is
talking to the wrong Temporal.

See [env.md](env.md) for the full variable list.

## Working on Ergane itself

When the repository under the CLI *is* Ergane, one script assembles the
environment from the host's encrypted secrets:

```bash
eval "$(scripts/ergane-env.sh)"
```

It **prints** `export` lines rather than setting them, so it must be eval'd.
Sourcing it appears to work and sets nothing, which then presents as a CLI that
cannot reach Temporal for no visible reason.

`scripts/ergane-env.sh --check` verifies the sources and reports variable names
and lengths without printing any value.
