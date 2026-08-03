# Contract: `factory.yaml` schema v1

Committed at the **target repo root**. Owned by component 2 (spec 002); consumed by
the gate runner here and by component 3's onboarding validation (required-check
correspondence). Parsed with `pyyaml` (`safe_load`), validated by
`factory/verify/factory_yaml.py`.

## Schema

```yaml
version: 1                      # REQUIRED — integer literal 1
runtime: python:3.11-bookworm   # REQUIRED — container image reference (string).
                                #   Recorded and validated for shape; container-
                                #   isolated execution is reserved for the sandbox
                                #   executor (research R3). v1 gates run as
                                #   subprocesses in the node worktree.
gates:                          # REQUIRED — at least one key
  test: "uv run pytest -q"      # each value: non-empty string, run via `bash -c`
  lint: "uv run ruff check ."   #   with cwd = the node worktree
  typecheck: "uv run mypy ."
timeouts:                       # OPTIONAL — seconds, per gate name
  test: 600                     # any gate not listed defaults to 600
```

## Validation rules

| rule | violation result |
|---|---|
| file exists at `<worktree>/factory.yaml` | `CONFIG_ERROR` — missing manifest |
| YAML parses to a mapping | `CONFIG_ERROR` — malformed |
| `version` present and `== 1` | `CONFIG_ERROR` — unsupported version |
| `runtime` non-empty string | `CONFIG_ERROR` |
| `gates` mapping, keys ⊆ {`test`, `lint`, `typecheck`}, ≥ 1 entry | `CONFIG_ERROR` — unknown gate name / empty |
| each gate command a non-empty string | `CONFIG_ERROR` |
| `timeouts` keys ⊆ declared gate names, values positive int | `CONFIG_ERROR` |
| no unknown top-level keys | `CONFIG_ERROR` |

Every `CONFIG_ERROR` yields a single `GateResult{name: "config", status:
CONFIG_ERROR, output_tail: <actionable message>}` and the verification verdict is
FAIL — **never pass-by-default** (spec edge case). The message names the exact
rule violated so the operator (or debugger persona) can fix the manifest.

## Semantics notes

- Gate names are fixed in v1 so component 3 can map merge-queue required checks
  1:1 to gates. Adding arbitrary named gates is a future schema bump (`version: 2`).
- Commands run with a scrubbed environment: minimal `PATH`/`HOME`/locale; no
  factory credentials are ever visible to gate subprocesses.
- Exit code 0 = pass, anything else = fail; exceeding the per-gate timeout =
  TIMEOUT (SIGTERM, then SIGKILL after 10s grace).
