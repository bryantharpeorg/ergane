# `ergane install`

> configure and verify the control plane

Interview the operator for the five control-plane subsystems, write
`~/.config/ergane/config.toml`, and verify what was written. Re-running loads
the existing file as defaults, so it is safe to run again to change one answer.

```
ergane install [--engine WHERE] [--target-repo PATH] [--lock-timeout SECONDS]
ergane install --verify
ergane install --requirements
ergane install --scan [--address ADDR]
ergane install --from-file FILE
ergane install --non-interactive
```

| flag | default | meaning |
| --- | --- | --- |
| `--verify` | | skip the interview: probe the declared subsystems and report one finding per check |
| `--engine` | asked | where the engine runs: `container`, `systemd` or `none` |
| `--requirements` | | print the model aliases and key-management endpoints the gateway must serve |
| `--scan` | | read-only discovery: list reachable LLM endpoints and their capabilities |
| `--address` | loopback candidates | probe this address instead of the defaults |
| `--from-file` | | read interview answers from a TOML file instead of stdin |
| `--non-interactive` | | use documented defaults for every question |
| `--lock-timeout` | `30` | seconds to wait for another `ergane install` to release the config lock before refusing |
| `--target-repo` | | repository the closing demonstration scaffolds against; interactive path only |

## The four modes

**Interview** (no flags) — asks, writes, verifies.

**`--verify`** — probes what is already declared and reports one finding per
check. This is the command for "is my control plane actually up", and it is the
one to run after changing anything upstream of Ergane.

**`--requirements`** — prints what the gateway must serve: the model aliases and
the key-management endpoints. Read this *before* configuring a gateway rather
than after, and hand it to whoever operates the gateway.

**`--scan`** — read-only discovery. Lists reachable LLM endpoints and what they
can do. `--address` points it somewhere other than the loopback candidates.

## Scripted configuration

`--from-file` reads a TOML answer file; documented defaults fill omitted fields,
and **a field with no safe default causes a refusal** rather than a guess.
`docs/ergane-install-answer.example.toml` in this repository is a worked example.

`--non-interactive` is the same contract with no file: every documented default,
and a refusal where there is none.

`--engine` is refused beside `--non-interactive` and `--from-file`, because both
of those configure only and never reach an engine step.

## Where the answers go

`~/.config/ergane/config.toml`. Environment variables **override** it — see
[env.md](env.md) — which is why a correctly-written config can still lose to a
stray export, and why [`ergane env --sources`](env.md) reports the route not
taken.

## The lock

Two `ergane install` runs cannot write the config at once. `--lock-timeout`
bounds the wait and then **refuses**; it does not block indefinitely.

## See also

- [`ergane env`](env.md) — what the CLI reads and which source won
- [`ergane worker`](worker.md) — the units that actually run the factory
- [`ergane engine`](engine.md) — the container tier
- [`ergane init`](init.md) — joining a repository, which is separate from configuring the host
