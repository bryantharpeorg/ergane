# `ergane env`

> show environment variables the CLI reads

List every environment variable Ergane reads, whether it is set, and its source.

```
ergane env [--sources]
```

| flag | meaning |
| --- | --- |
| `--sources` | report which source won for each resolved value, **and the route not taken** |

## The bare listing

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

Each line carries the name, the value where it is safe to print, the default in
parentheses, and a bracketed disposition.

**Secret values are redacted in the bare listing.** `[REDACTED]` means set, not
empty.

## The variables

| variable | default | what it does |
| --- | --- | --- |
| `TEMPORAL_ADDRESS` | `localhost:7233` | the Temporal server the CLI and worker dial |
| `TEMPORAL_NAMESPACE` | `ergane` | the namespace within it |
| `LITELLM_PROXY_URL` | control-plane config | the gateway endpoint |
| `LITELLM_MASTER_KEY` | control-plane config | the gateway's master key, used to mint per-epic virtual keys |
| `TELEGRAM_BOT_TOKEN` | — | the operator bridge's delivery credential |
| `ERGANE_LEDGER_PATH` | `.factory/ledger.db` | the usage ledger [`ergane usage`](usage.md) reads |
| `ERGANE_VERIFICATION_DB_PATH` | `.factory/verification.db` | the verification store [`ergane build attempts`](build.md) reads |

The listing is generated from the same registry the resolution uses, so a
variable that exists in the code appears here without anyone updating a list.

## Environment overrides config

A set variable **wins** over `~/.config/ergane/config.toml`. That is the single
most common cause of a correctly-configured CLI talking to the wrong Temporal or
the wrong gateway, because a shell export from an hour ago is invisible in the
config file.

`--sources` is the diagnosis: it says which source won for each resolved value
**and names the route not taken**, so a config value that lost is visible rather
than absent.

## Working on Ergane itself

One script assembles the environment from the host's encrypted secrets:

```bash
eval "$(scripts/ergane-env.sh)"
```

It **prints** `export` lines rather than setting them, so it must be eval'd —
not sourced, not run bare. Sourcing it appears to work and sets nothing, which
then presents as a CLI that cannot reach Temporal for no visible reason.

```bash
scripts/ergane-env.sh --check
```

verifies the sources and reports names and lengths without printing any value.

## See also

- [`ergane install`](install.md) — writes the config these variables override
- [`ergane --version`](README.md) — prints the endpoints without dialing them
