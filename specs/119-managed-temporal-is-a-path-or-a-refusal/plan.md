# Implementation Plan: managed Temporal is a path or a refusal

**Spec**: `specs/119-managed-temporal-is-a-path-or-a-refusal/spec.md`

Carry the declared mode into the layout, stop the wrapper eating arguments, and
make the server able to start and verification able to notice.

## What already exists, and where

- **The layout resolver**: `resolve_layout(*, home, install_root, interpreter,
  unit_dir, generated_dir, env_command)` (`factory/supervision/units.py:255`).
  Six keyword arguments, none of them the mode; its docstring (`:264-268`) says
  it resolves "where this installation actually is", from the filesystem. That is
  a coherent job and US1 must extend it without turning it into a config reader —
  the mode is *passed in*, like every other parameter there.
- **The field and its default**: `temporal_mode: str = "external"`
  (`:201`) on the layout dataclass.
- **The predicate and its false docstring**: `_temporal_managed(layout)`
  (`:324-332`). FR-004 exists because this docstring asserts a mechanism that is
  absent; US1-S5 turns it into a test rather than a comment.
- **The generator**: `generated_files(layout)` (`:336`), "Every file `install`
  writes, rendered from `layout` and nothing else" — which is exactly why a
  layout carrying the wrong mode writes the wrong file set, and why fixing the
  layout fixes the generation with no change here.
- **The wrapper template**: the heredoc ending at `:600` —
  `{environment}exec "${{3:-{layout.interpreter}}}" -m "$1"`, preceded by
  `cd "${{2:-{layout.install_root}}}"` (`:597`). The three positionals are
  module, working directory, interpreter.
- **The verification arm**: `factory/controlplane/verify.py:606-616`, the
  managed-Temporal check that passes without dialling.

## Traps

**Trap 1 — the wrapper fix is not `"$@"`.** The obvious patch is to replace
`-m "$1"` with `-m "$@"`, and it is wrong: `$2` and `$3` are the working
directory and the interpreter, not module arguments, so `"$@"` would pass both to
the module as flags. The correct shape consumes the three positionals first —
`shift` past them once their values are captured — and then forwards what
remains. US2-S3 is the scenario that catches the wrong fix: overrides must still
apply *and* must not reach the module.

**Trap 2 — `resolve_layout` must not learn to read configuration.** Its whole
value is that it resolves from the filesystem and its arguments. Adding a
manifest read inside it makes it untestable and couples supervision to the config
loader. Pass the mode in from the caller that already knows it, exactly as every
other parameter arrives.

**Trap 3 — a silent default is the defect, so do not add another one.** FR-003
requires a refusal when the mode cannot be determined. It is tempting to keep
`"external"` as a safe fallback; that is precisely the behaviour that let this
survive three patches, because external mode fails in a way that looks like the
operator's Temporal being down. Refuse and name what could not be read.

**Trap 4 — FR-004 is a test, not a comment edit.** Rewriting the docstring to
match reality is necessary and insufficient. US1-S5 asserts the *behaviour* the
docstring claims, so the two cannot drift again. A story that only edits prose
has not satisfied it.

**Trap 5 — the ordering dependency needs both directions of the systemd
contract.** `After=` alone orders without requiring; `Wants=` requires without
ordering. A unit that carries only one still burns its start limit in the case
this fixes. State which pair is used and why in the generated unit's own comment.

**Trap 6 — uninstall must not dial anything.** FR-011. The current failure is a
verb that removes units depending on the service those units run, which means a
broken installation cannot be cleaned up — the exact state an operator reaches
*because* of this defect. Removing units is a filesystem and systemd operation
and needs no Temporal.

**Trap 7 — the verification fix must fail closed.** FR-009 changes a check that
passes into one that dials. A dial that treats "connection refused" as
inconclusive and passes anyway has reproduced the defect with more code. Failing
to reach the server is a failure.

**Trap 8 — worker install's report is what an operator reads instead of the
journal.** FR-010: it currently names the probe timer and nothing else, while
three services fail behind it. Report each service and its state at return time,
not a summary that a started-but-failing unit passes.

## Sizing

US1 is a parameter, a refusal and a docstring made true — small, with trap 2 and
trap 3 the risks. US2 is one line of shell and the epic's easiest thing to get
subtly wrong (trap 1). US3 is the largest: a directory, unit ordering, a real
dial, a fuller report and an uninstall that stops depending on a service.

If an attempt is adding a deployment mode or vendoring a server binary, it has
gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves generation and argument passing. Only a real host proves the path,
and this defect is defined by a green check over a machine with nothing running:

```bash
# On a host with no Temporal server, declaring managed mode:
eval "$(scripts/ergane-env.sh)"
uv run ergane install --from-file <answers.toml>   # mode = "managed"
uv run ergane worker install
systemctl --user status ergane-temporal.service ergane-worker.service ergane-bridge.service
uv run ergane install --verify
```

The demonstration succeeds when the Temporal unit exists and is active, the
worker and bridge are active rather than in a start-limit failure, and `--verify`
passes *after* the server is up and fails when it is stopped. Run `--verify` with
the server deliberately stopped and paste that failure too — a check that can only
pass proves nothing, and the ability to fail is what this spec is buying.
