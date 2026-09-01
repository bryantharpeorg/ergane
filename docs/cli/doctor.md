# `ergane doctor`

> run all registered probes

```
ergane doctor [--db PATH]
```

| flag | default | meaning |
| --- | --- | --- |
| `--db` | resolved runtime root / `doctor.db` | path to the findings store |

Runs every registered probe and **files any findings** into the ledger. It is
not a read-only command: a probe that fails writes a row.

## What a probe is

A check the factory runs against itself — the state of the runtime root, the
consistency of registry entries, the shape of things that have gone wrong
before. Probes live in `factory/doctor/probes.py`; discovery is by registration,
so a new probe runs the moment it exists and there is no list to update.

## Reading the result

The findings a run produces are the answer, and they are read with
[`ergane findings list`](findings.md) rather than from `doctor`'s own output.
The two commands share a store: `doctor` writes, `findings` reads and manages.

A probe that fires on something already in the ledger records a **recurrence**
against the same key rather than a new finding. That count is what later makes
"this has happened repeatedly" a fact, so running `doctor` regularly is what
gives the ledger its resolution.

## When to run it

After anything unusual — a killed epic, a recovered runtime root, a host that
was rebooted mid-attempt — and on a schedule if you want the recurrence counts
to mean anything. A probe that only ever runs during an incident tells you what
was broken then, not how often it breaks.

## See also

- [`ergane findings`](findings.md) — read, resolve, triage and promote what this files
- [`ergane install --verify`](install.md) — probes the control plane rather than the factory's own state
