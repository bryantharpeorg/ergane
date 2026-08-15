# Plan: Ergane Install — the control plane's config

All line references were re-read against the tree at `d13fc4a` on 2026-08-14,
after 040-manifest-rename landed. Grep the construct beside each anchor rather
than trusting the number — see trap 8.

This epic is the config plane and nothing else. If you find yourself writing a
Temporal workflow, a systemd unit, or a messenger adapter, you have wandered
into 041 or 042 — stop and read this plan's scope fence (trap 1).

## What has landed since this plan was written

**US1 landed 2026-08-14** (`5b4351a`, PR #68, first attempt). The typed shape
exists at `factory/controlplane/config.py`: `ControlPlaneConfig` (`:99`),
`ControlPlaneConfigError` (`:74`, in the `FactoryConfigError` grammar),
`resolve_config_path` (`:174`, already following `resolve_env_path` with
`ERGANE_CONFIG_PATH`/`FACTORY_CONFIG_PATH`), `load_controlplane_config` (`:197`)
and `parse_controlplane_config` (`:237`). US2 consumes *that*, as it exists on
the branch — not this plan's description of it. Rebuild none of it; US1's tasks
are provenance.

**034/us1 landed the same day** (`7055ea5`, PR #69), which discharges the
"if 034 landed first" conditionals below: the prompter seam exists at
`factory/cli/init.py:42` (`_prompter_factory`, `_TerminalPrompter` at `:53`) and
US3's interview reuses it (trap 6). The XDG *state*-home resolver and the lock
do **not** exist yet — 034/us2 has not landed — so trap 5's lock guidance
stands.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| **The gather/judgment split, as a protocol** | `factory/doctor/probes.py:69` — grep `class Probe` (`name`, `gather()`, `evaluate(snapshot)`) | US2 — FR-006's "015 pattern" is this protocol, already written |
| Its snapshot dataclasses, as shape precedent | `factory/doctor/probes.py:82`–`:108` — grep `class KeyListSnapshot` | US2 — one frozen snapshot per probe |
| A worked probe, gather and judgment both | `factory/doctor/probes.py:243` — grep `class OrphanedKeyProbe` | US2 — copy its shape, not its subject |
| The "dependency won't answer" signal | `factory/doctor/probes.py:30` — grep `class ServiceNotAnswering` | US2 — distinct from skipped-by-declaration; trap 3 |
| **The check-finding grammar the spec actually means** | `factory/mergequeue/models.py:208` — grep `class Finding` (`check`, `passed`, `detail`) | US2 — trap 2, and read it before you write a line |
| The manifest parser's error grammar | `factory/verify/factory_yaml.py:87` — grep `class FactoryConfigError` (`rule`, `problem`, `source`) | US1 — FR-002's "stable named rules" is this shape, for a different file |
| Its rejection style, worked | `factory_yaml.py:212` (`_read_gates`), `:172` (`_read_version`) | US1 — how a violation names the rule and renders the value |
| **The env-variable resolution convention 040 just set** | `factory/env.py` — grep `def resolve_env_path` (`ERGANE_*` wins, `FACTORY_*` honored, one `DeprecationWarning` per process via `_WARNED`) | US1 — trap 9; FR-001's config-path override is a new operator-facing variable and must arrive already following this |
| The persona registry FR-014 must stay compatible with | `factory/config.py:41` (`DEFAULT_REGISTRY_PATH`), `:65` (`class Persona`), `:88` (`load_personas`) | US1 — the `direct`-mode LLM block's shape |
| The LLM client the LLM probe drives | `factory/usage/litellm_client.py:107` (`LiteLLMClient`), `:56`/`:57` (`PROXY_URL_ENV`, `MASTER_KEY_ENV`) | US2 |
| The Telegram sender the escalation probe delivers through | `factory/notify/service.py` — grep `class CallbackBridge`; live suite at `tests/test_live_notify.py` | US2 — today's transport; 041 replaces the gather, not the judgment |
| The live-double / auto-skip discipline | `tests/test_live_proxy.py:1-40` (its docstring is the doctrine), markers in `pyproject.toml:33-37` | US2 — SC-006's "gather executes against a live double" |
| The CLI error boundary | `factory/cli/errors.py` — grep `class OperatorError` | US1–US3 |
| The `input()` precedent and its limits | `factory/cli/nouns/build.py:420`; test at `tests/test_ergane_build.py:867` | US3 — same limit 034 hit; trap 6 |
| **034/us1's prompter seam — landed** | `factory/cli/init.py:42` (`_prompter_factory`), `:53` (`_TerminalPrompter`) | US3 — trap 6; reuse, do not build a second |
| **This spec's own landed US1** | `factory/controlplane/config.py` — see "What has landed" above | US2, US3 — the typed shape and the rule table |

**Deliberately absent, re-verified by grep over `factory/` at `0bf0c93` on
2026-08-14:** file locking (zero hits for `fcntl`, `flock`, `filelock`) and any
TOML *writing*. XDG config resolution and `tomllib` reading are no longer
absent — US1 landed both. Python is `>=3.11` (`pyproject.toml:5`), so `tomllib`
reads TOML in the stdlib — **and nothing in the stdlib writes it.** See traps 4
and 5.

## Traps

### Trap 1 — this epic builds no workflow, no unit, and no adapter

The spec you are implementing was split out of a seven-story draft on
2026-08-13. Three of its subsystems describe things built in *other* epics:
managed Temporal and every systemd unit are 042; the EscalationWorkflow and
the messenger adapter seam are 041. This epic parses their configuration and
probes what already exists. The temptation is US2's escalation probe — "deliver
a test escalation and watch it expire" needs a lifecycle, so build one? No.
Deliver through 008's existing Telegram sender, behind the `Probe` protocol, so
041 later swaps one `gather()` and leaves every judgment untouched. The story's
own scope note says this; FR-006's last clause makes the deferral a *reported
finding* rather than a silent partial pass.

### Trap 2 — "the doctor's findings grammar" names a type that is not what you want

FR-006 says findings are "check slug, passed, actionable detail". There are two
`Finding` classes in this tree and **that description matches the other one**:

- `factory/mergequeue/models.py:208` — `check`, `passed`, `detail`. This is the
  grammar FR-006 describes, and the one to render.
- `factory/doctor/models.py:30` — `key`, `category`, `severity`, `status`,
  `refs`, `occurrences`, `first_seen`, `promoted_spec`… a **persistent ledger
  row**, written by `cli/doctor.py:222` (`_report_if_new`) and counted for
  recurrence.

Take "the doctor's grammar" literally and every `install --verify` run files
rows into the findings ledger, where a host with a down OTLP collector becomes
"recurrence 14" beside real defects — corrupting the count that decides what
gets promoted to the constitution. Reuse the doctor's **`Probe` protocol**
(that part is exactly right); render the **mergequeue check grammar**; write
nothing to the findings store.

### Trap 3 — three different kinds of "this check did not really run"

They are not interchangeable and US2 needs all three distinguishable:

- **Skipped by declaration** — the operator set `memory = none`. A pass-shaped
  finding saying the absence was chosen (US2-S5).
- **Deferred to a later epic** — the escalation lifecycle half, which 041 owns.
  A finding that says so (US2-S3, FR-006's last clause).
- **Dependency not answering** — `ServiceNotAnswering` (`probes.py:30`), the
  probe's own machinery failing rather than the subsystem being unhealthy.

Collapse any two and the operator reads "green" over something nobody checked.
That is the 015 regression restated, and SC-006 exists because it already
shipped once.

### Trap 4 — the stdlib reads TOML and does not write it, and US3-S2 is a round-trip claim

`tomllib` (3.11+) is read-only. There is no stdlib writer. Meanwhile US3-S2
asks that a re-run changing the OTLP endpoint produce a diff touching *exactly*
the `[telemetry]` block — which, if you parse-mutate-serialize with any plain
writer, is false the first time an operator has a comment or a blank line in
their file.

The resolution, and take it rather than re-deriving it: **render the file
deterministically from the typed shape**, every time, in a fixed block and key
order. Then "the diff touches exactly that block" is true by construction, a
re-run with unchanged answers is byte-identical for free (FR-007), and no
round-trip library enters the dependency list. Say in the commit that a
hand-edited file's comments are not preserved, because that is a real
consequence and the operator should meet it in a doc rather than in a diff.

### Trap 5 — 033 and 034 both introduce XDG resolution and both introduce a lock

FR-001 puts the config under the XDG *config* home and 034 FR-006 puts the
registry under the XDG *state* home. FR-007 locks the config file and 034
FR-008 locks the registry file. Neither mechanism exists anywhere in `factory/`
today — grep found zero hits for `XDG_STATE_HOME`, `fcntl`, `flock`,
`filelock`. The two epics are not ordered against each other.

**Whichever lands second reuses what the first built** — one path resolver
taking which home it wants, one lock helper. Check the tree before writing
either; if `specs/034-ergane-init` has landed, its US2 has both. Two resolvers
disagreeing about where state lives is a bug that surfaces as an empty registry
on a host that has one.

Re-verified against `0bf0c93` on 2026-08-14: `XDG_CONFIG_HOME` now has hits —
this spec's own US1 landed the config-home resolver
(`factory/controlplane/config.py:174`, `:190`). `XDG_STATE_HOME`, `fcntl`,
`flock` and `filelock` are still zero. If 034/us2 lands before US3 runs, its
state-home resolver and lock exist and are reused; otherwise US3's lock is the
first lock in this tree, and 034 reuses *it*.

Both need a test override, and it belongs in 030's session fixture
(`tests/conftest.py`, grep `_isolated_test_store`) so isolation is the default
rather than something each test remembers. A test that writes the operator's
real `~/.config/ergane/config.toml` has rewritten this host's control plane.

The override's *name and resolution* are no longer a free choice. 040 landed
`factory/env.py` and with it the house rule for every operator-facing path
variable: an `ERGANE_*` name that wins, a `FACTORY_*` legacy name still honored,
a conflict reported once, and one `DeprecationWarning` per process rather than
one per read. Do not hand-roll `os.environ.get` for this epic's override —
`resolve_env_path(new, old, default)` already exists and a second convention
introduced one epic later is the drift this whole rename was spent avoiding.

### Trap 6 — a five-subsystem interview cannot be a monkeypatched `input()`

Identical to 034's trap: the only precedent is one y/N at
`build.py:420`, tested by rebinding `builtins.input`
(`tests/test_ergane_build.py:867`). US3 branches on mode per subsystem, loads
existing values as defaults, and validates each answer at entry. 034/us1 has
landed exactly the seam this calls for — `_prompter_factory` at
`factory/cli/init.py:42`, `_TerminalPrompter` at `:53` — so use it. A second
prompter convention one epic later is the same drift trap 5 exists to prevent.

### Trap 7 — the probe that hangs is the probe that passed review

FR-006 bounds every probe by an explicit timeout, and US2-S4 makes it a
criterion. The live-tier lesson already recorded in this repo is that a dead
port does not raise what you expect — `temporalio` raises `RuntimeError` against
a closed socket, not a connection error. So prove the timeout the way that
lesson says: point the probe at `127.0.0.1:1` and assert it fails *within* its
bound, rather than asserting on an exception type you predicted.

### Trap 8 — anchors rot, and this tree is moving fast

Nineteen stories landed on 2026-08-13 alone. Grep for the construct —
`class Probe`, `class Finding`, `FactoryConfigError`, `LiteLLMClient`,
`load_personas`, `_isolated_test_store` — and if a citation here disagrees with
the tree, the tree wins and you say so in the commit message.

### Trap 9 — the seam that makes a gather testable is the seam that hides it, and it shipped yesterday

The Verification section below says SC-006 exists because 015 shipped a command
that could not start. That is no longer the only example, and the newest one is
in the epic immediately before this one.

040-manifest-rename/US2 added `ergane repo migrate-runtime-root`. Its refusal
path calls a module-level client seam, `_temporal_client_factory`, defaulting to
`_open_client()` (`factory/cli/repo.py:63`). `_open_client` reads
`os.environ.get(...)` at `:51`–`:52` — and the module never imports `os`. Every
test rebinds the seam, so the real function's body is executed by nothing. The
suite reported **2265 passed**, the judge passed it, the merge queue landed it,
and the verb cannot run:

```
$ ergane repo migrate-runtime-root
ergane: unexpected error (name 'os' is not defined)
```

Filed as `cli/migrate-runtime-root-cannot-run` (critical, 2026-08-14).

This epic is more exposed to that failure than 040 was. US2 is *five* probes
whose entire purpose is touching the world — a proxy, a Temporal server, a
messenger, an OTLP endpoint — and every one of them will be scripted in tests
for exactly the right reasons. The gather/judgment split is correct; what it
cannot do by itself is prove the gather runs. SC-006's live double is not
ceremony, and "the judgment is table-tested and the gather is obvious" is the
sentence that precedes this defect every time.

Concretely: for each probe, at least one test must execute the **real**
`gather()` with the seam unrebound, against a live double or a closed port, and
the diff must show which test that is. A probe whose real `gather()` is never
entered by any test in the diff is not implemented — it is described.

### Trap 10 — a live Temporal double that outlives its test kills the host

The live double T018 wants for the Temporal probe is exactly the process class
that OOM-killed this host on 2026-08-11: 8,131 orphaned `temporal-test-server`
processes holding 123 GiB, each orphaned when its parent died to a bare signal,
because nothing reaped them. The finding
`hardening/orphaned-test-servers-exhaust-host-memory` is open, at outage
severity. 027 and 030 cleared the fixtures, gates and adapter; the surviving
discipline is the `try/finally` shutdown bracket — see
`tests/test_verification_flow.py:466-470`, where every `WorkflowEnvironment` is
shut down in a `finally` no matter how the test ends. Start your double the
same way or reuse an existing fixture; never a bare `subprocess.Popen` in a
test body. A probe suite that leaks one server per run recreates the outage at
exactly the cadence `install --verify` is meant to be run.

## Approach

### US1 — the parser, and only the parser (LANDED `5b4351a` — provenance only)

1. Resolve the config path from the XDG config home with an override (trap 5).
   Read with `tomllib`.
2. Parse to a frozen typed `ControlPlaneConfig`, five mode-discriminated
   blocks. Every violation raises the `FactoryConfigError` shape
   (`factory_yaml.py:80`) with a stable rule slug — unknown key, unknown mode,
   two namespaces, secret-shaped value, unregistered adapter, and
   `temporal.mode = "managed"` before 042 exists.
3. The secret-shape refusal (FR-003) is a *shape* check on the value, not a
   guess at intent: a field named `*_env` whose value looks like a credential
   rather than an identifier. Table-test it, and include the two shapes this
   host actually uses (`sk-…`, a bot token's `digits:base64` grammar).
4. FR-013's fail-closed belongs to the resolver, so every command that consults
   the config inherits it rather than each remembering.

### US2 — five probes, each a gather and a judgment

1. Implement each as the `Probe` protocol (`probes.py:69`): a thin `gather()`
   that touches the world and returns a frozen snapshot, a pure `evaluate()`
   over it. Each probe reads its subsystem's block from the **landed**
   `ControlPlaneConfig` (`factory/controlplane/config.py:99`), never from raw
   TOML. The judgment is table-tested with no fakes; the gather is exercised
   at least once against a live double (SC-006, trap 10).
2. Render `Finding(check, passed, detail)` — the mergequeue grammar (trap 2) —
   one per check, no masking, non-zero exit on any failure.
3. Details name what was *done*, not that it was fine: "completed a 1-token
   completion against persona `implementer`" beats "ok".
4. Distinguish the three not-really-run cases (trap 3).
5. Bound every probe and prove the bound against a closed port (trap 7).

### US3 — the walkthrough, which never writes what the parser refuses

1. Prompter behind a seam (trap 6). Mode first per subsystem, then only that
   mode's fields.
2. Validate each answer with US1's own rules at entry — one rule table, not two.
3. Render the file from the typed shape, deterministically (trap 4).
4. Hold an exclusive lock on the config path for the whole run (trap 5), and
   test the contended case.
5. End by running US2's verify; its findings are the command's final output.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Three stories instead of one command | US1 is consumed by everything and provable with no I/O at all; US2 is the only story needing live doubles; US3 depends on both and is pure ergonomics. Merging them would put a parser's table tests and a live-double harness in one attempt. |
| A config file at all, when env vars work today | Habits are not a control plane. The env-var setup is undeclared, unprovable, and re-derived per operator — and the one thing it cannot do is tell a fresh host what it is missing. |
| Deterministic rendering rather than a TOML round-tripper | Trap 4. It buys US3-S2 and FR-007's byte-identity by construction and adds no dependency. |
| Probes split gather/judgment even where the gather is three lines | SC-006 exists because 015 shipped a command that could not start: the split that makes judgment testable is the split that hides an unrunnable gather. The discipline is the mitigation. |

## Verification

`uv run pytest -q` green in the worktree before and after each story — safe from
any directory as of 030.

Green is necessary and not sufficient, twice. SC-006 is a claim about *which
code paths ran*, which a green suite cannot express: every probe's gather must
execute against a live double at least once, and the diff must show it. And the
timeout bound (US2-S4) is proven by a closed port, not by an exception type
someone predicted (trap 7).
