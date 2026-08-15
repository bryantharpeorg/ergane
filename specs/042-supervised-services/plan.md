# Plan: Supervised services

All line references were re-read against the tree at `ca122ad` on 2026-08-15,
after 033's config parser and 011-agent-sandbox's first stories landed. Grep
the construct beside each anchor rather than trusting the number — see trap 8.

Findings this spec closes, narrows, or points at:

| Finding | Sev | Disposition |
| --- | --- | --- |
| `hardening/stack-supervision` | critical, 2× | The driver. Its scope correction is load-bearing: liveness alone would NOT have prevented the 2026-08-11 outage — memory headroom and orphan count are why the probe checks more than `is-active` |
| `hardening/orphaned-test-servers-exhaust-host-memory` | critical | Closed by FR-006 (trap 3); narrowed first by 011's boundary — see Assumptions |
| `hardening/operator-channel-has-no-listening-half-supervised` | critical | Closed by US2's bridge unit + probe — trap 10 explains why the bridge is the unit whose death is otherwise invisible |
| `hardening/agent-pkill-kills-the-live-worker` | critical | Fixed at the root by 011/US4 (signal isolation); trap 9's spelling discipline stays as defense in depth |
| `hardening/self-landing-stales-the-running-worker` | critical | **Out of scope, deliberately** — see the spec's Out of Scope for why unit-liveness cannot see it |

## Read the prior art first. It is not in this repository.

Five systemd user units and a 6 KB probe script are running on the operator's
host right now, hand-written on 2026-08-12, and they live in a **different
repo**: `/home/admin/code/homelab/infra/ergane-supervision/`. They are the
specification of intent for this epic. Read them before you write anything:

```
ergane.slice              ergane-temporal.service   ergane-worker.service
ergane-bridge.service     ergane-probe.service      ergane-probe.timer
ergane-probe.sh           ergane-worker-run.sh      README.md
```

Your job is not to invent supervision. It is to make the engine *generate* that
supervision, portably, with the alert path going through 041's adapter instead
of a hardcoded `curl`. Every trap below is a line from that prior art, and each
one was paid for.

If the directory is absent on the host you are working on, say so in your commit
and implement from the quoted excerpts here — but do not silently skip reading
it. The lessons are not reconstructible from first principles; they are
reconstructible from an outage.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| **The unit set, as prior art** | `/home/admin/code/homelab/infra/ergane-supervision/*.service`, `*.timer`, `*.slice` | US2, US3 — the design input |
| **The probe, as prior art** | same directory, `ergane-probe.sh` — read its header comment in full | US1, US2 |
| 041's adapter, as a plain library | 041 FR-002 — callable with no Temporal client and no workflow context | US1 — this epic is the caller that requirement exists for |
| 033's typed config, **landed** | `factory/controlplane/config.py` — `Temporal` block at `:146` (mode/address/namespace), `Escalation` at `:165`, managed refusal `RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED` at `:54` | US1, US3 — US3's T027 removes that refusal rule |
| The XDG state home resolver | 034/us2's registry state home if landed by dispatch (check `ergane spec landed specs/034-ergane-init --default-branch ergane-buildout`); otherwise derive from `XDG_STATE_HOME` directly, matching `resolve_config_path`'s pattern (`factory/controlplane/config.py:174`), and say which in the commit | US2 — the probe's status/heartbeat files |
| The open-epic capacity read | `factory/activities/roadmap_activities.py:469` (`count_open_epics`) | US2 — FR-012's refusal |
| The CLI error boundary | `factory/cli/errors.py` — grep `class OperatorError` | US1–US3 |
| The source-scanning test precedent | `tests/test_gh_client.py` — grep `test_no_code_path_passes_delete_branch` | US2 — SC-006's "no path outside the installation" |

## Traps

### Trap 1 — `KillMode=control-group` is the whole point, and its absence is invisible

From `ergane-worker.service`, verbatim:

```
# KillMode=control-group is the point, not a default worth losing: agents, gate
# subprocesses and any temporal-test-server they spawned are all in this unit's
# cgroup, and stopping the unit must take the whole tree. A bare kill of the
# worker pid is what leaves 66 MiB orphans behind on PID 1.
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec=120
```

A generated unit missing this looks correct, starts correctly, restarts
correctly, and leaks a 66 MiB process every time an agent is killed. FR-004 and
SC-002 exist to make it provable: count processes before and after stopping a
unit that has children, and paste the counts.

### Trap 2 — the probe must be outside the slice it watches

From `ergane-probe.service`, verbatim:

```
# Deliberately NOT in ergane.slice: the supervisor must outlive what it watches.
# A probe inside the contained slice would be reclaimed alongside the leak it
# exists to report.
```

Every other generated unit goes in the slice. The probe does not. Getting this
backwards produces a supervisor that dies exactly when it is needed, and no test
that only checks "the probe ran" will notice.

### Trap 3 — reaping has three conditions and each one matters

From `ergane-probe.sh`:

```bash
mapfile -t orphans < <(ps -eo pid=,ppid=,etimes=,comm= \
  | awk -v age="$ORPHAN_MIN_AGE_S" '$4 ~ /^temporal-test-s/ && $2 == 1 && $3 > age {print $1}')
```

Three conditions, three reasons:

- **`^temporal-test-s`, not the full name.** `comm` truncates at 15 characters.
  Match the full `temporal-test-server` and you match nothing, forever, silently.
- **`$2 == 1`** — reparented to PID 1. A test server with a live parent is a
  running test.
- **`$3 > age`** (default 120s) — grace, so a fresh spawn is never raced. Reaping
  a two-second-old server kills a test that was working.

Any one of these dropped turns a safety net into a saboteur. Test all three:
seed an orphan, a fresh orphan, and a parented process, and assert exactly one
is reaped.

### Trap 4 — alerts are edge-triggered, and the heartbeat is why silence means something

From the probe's header, verbatim:

```
# Alerts are edge-triggered: a message on every status change, plus one daily
# heartbeat so silence is distinguishable from death.
```

The timer fires every two minutes. An alert per firing is a channel the operator
mutes within a day, and a muted channel is worse than no channel because it
looks supervised. The state is two files under the state home — last status,
last heartbeat — and the send decision is a small table over (status, previous
status, time since heartbeat, whether anything was reaped). FR-013 is this.

### Trap 5 — the probe reports; it does not remediate

From the header, verbatim:

```
# What it does NOT do: restart things. systemd owns restarts. Liveness alone was
# never the gap — a restart into an already-dying box makes an OOM storm worse,
# which is exactly why this reports memory pressure instead of reacting to it.
```

The instinct on reading "the worker is down" is to restart it. Do not add that.
FR-014 makes reaping the sole exception, and only because nothing else in the
system will ever reap an orphan.

### Trap 6 — a probe that cannot escalate must be loud

From the escalate block, verbatim:

```bash
  # Never fail silently here: a probe that cannot escalate is indistinguishable
  # from a healthy floor, which is the exact failure this whole unit exists to end.
```

And from the unit: `SuccessExitStatus=0 1`, because a degraded verdict is a
report, not a unit failure. Keep both halves — the exit code discipline and the
loud complaint on an undeliverable alert (FR-015).

### Trap 7 — every path in the prior art is unportable, and that is the part you must change

The live units hardcode `/home/admin/code/ergane`,
`/home/admin/code/homelab/infra/ergane-supervision/...`,
`/home/admin/.temporalio/bin`, and a sops file at
`$HOME/.config/homelab/ergane.enc.env`. All of it is correct for this host and
wrong for the product. Generated units reference only the operator's own
installation — resolved paths, not literals from this plan. SC-006 asserts it by
scanning the generated unit text, and it is the single clearest way this epic
can fail while looking finished.

The credential path is the sharpest case: the prior art greps a decrypted sops
blob for `TELEGRAM_BOT_TOKEN`. **Do not carry that forward.** The alert goes
through 041's adapter, which gets its credentials the way 033's config says.

### Trap 8 — anchors rot, and the prior art is not version-controlled with this tree

The homelab copies can change without this repository noticing. Quote what you
read, in your commit, with the date — and if a unit on the host disagrees with
this plan, the host wins and you say so.

### Trap 9 — the `ExecStart` spelling is load-bearing, and the obvious one is wrong

The prior art's `ergane-worker.service` does not exec the worker. It runs a
wrapper, and the wrapper ends:

```bash
uv sync --locked --quiet
exec "$ERGANE/.venv/bin/python3" -m factory.worker
```

Not `uv run python -m factory.worker`, which is what every other invocation in
this repository uses and what a generator will reach for. From the wrapper's own
comment, verbatim:

```
# Why the indirection matters: on 2026-08-12 the 032 agent ran
# `pkill -f "python -"` inside its worktree to clean up test servers. That
# pattern matched this unit's `uv run python -m factory.worker` command line
# and the bridge's, and SIGTERMed both — killing the worker that was running
# the agent. ergane-temporal survived only because it is a Go binary. The
# `python3 -m` spelling below carries no "python -" substring, which is
# exactly why the venv's own interpreter child survived that sweep.
```

A generated unit spelling it `uv run python -m factory.worker` is correct,
starts, restarts, and dies the next time an agent sweeps its own strays. Assert
the generated text on the same pass as SC-006: no supervised unit's command line
contains the substring `python -`.

The root defect — an agent able to signal anything on the host — is fixed as
of 2026-08-15: 011-agent-sandbox/US4 denies cross-boundary signals outright
(`--unshare-pid`; its US4-S3 scenario is literally `pkill -f "python -"`
failing to reach the worker). Keep the spelling discipline anyway, and say why
in the commit: it costs nothing, and it still protects the one caller class
the boundary does not cover — operator-side and boundary-disabled runs, the
same class that keeps FR-006's reap alive.

The wrapper's other half is a design question this epic must answer rather than
inherit: systemd cannot `eval` a command substitution, and the environment
arrives from a command that emits `export` lines. So the engine either generates
a wrapper script alongside each unit, or resolves the environment at install
time into the unit. Choose deliberately and record why — the prior art chose the
wrapper specifically so secrets never touch disk, and that reason survives the
rename of everything around it.

### Trap 10 — the bridge is the unit whose death is invisible, so its unit is the one that matters most

From `hardening/operator-channel-has-no-listening-half-supervised`, observed
2026-08-12: a question reached Telegram at 14:09Z, the operator answered at
15:08Z, and the answer fell on the floor — no process was running `run_bridge`
(`factory/notify/service.py:365`), so nothing polled for replies. The dangerous
property is the asymmetry: the SENDING half is a workflow activity that needs
no bridge, so questions keep flowing outward and the channel looks healthy
from the factory's side while every inbound answer is lost. Nothing inside the
factory can notice this — which makes the probe's liveness check on the bridge
unit the *only* watcher the answering half has. Treat `ergane-bridge` inactive
as exactly as page-worthy as the worker being down (FR-007 draws no
distinction between units; this trap is why it must not).

## Approach

### US1 — the alert that works when Temporal does not

1. A small module with one entry point: render an alert (service, condition,
   duration) and hand it to 041's adapter. No Temporal import on this path at
   all — assert that by scanning the module's source, not by intending it.
2. Swallow send failures into the log (FR-002) and complain loudly when no
   delivery is possible at all (FR-015, trap 6).
3. The test that matters runs with no Temporal server and no client
   constructed. 042 exists for that case.

### US2 — the worker's units, the slice, and the probe

1. Generate the unit text from resolved paths (trap 7) with the slice, the kill
   semantics (trap 1) and a bounded restart (`StartLimitIntervalSec` /
   `StartLimitBurst` in the prior art).
2. Install, enable, and enable linger. `uninstall` removes exactly what install
   wrote and reports a same-named unit it did not write (FR-008) — record
   provenance at install time rather than guessing at uninstall time.
3. The probe: unit liveness, TCP reachability, host memory headroom, orphan
   count and reap (trap 3), slice memory as a note. Outside the slice (trap 2).
   Edge-triggered with a heartbeat (trap 4). Reports, never remediates (trap 5).
4. FR-012's refusal uses the existing capacity read, not a new mechanism.

### US3 — managed Temporal

1. Generate the server unit with persistent storage. From the prior art, and it
   is the one flag whose absence is silent:

   ```
   # --db-filename is what makes epic state survive a restart (D-006);
   # without it every reboot silently discards in-flight workflow history.
   ```

   SC-004 is the proof: write history, restart the unit, read it back.
2. Clear 033's parse-time refusal of `managed` (FR-009) — that refusal names
   this epic, so landing it is part of the story.
3. `external` installs nothing and renders a finding saying whose contract the
   uptime is (FR-010) — a silent pass here is how a remote outage becomes a
   mystery.
4. Refuse managed mode at walkthrough time on a host without systemd user
   sessions (FR-011), not at unit-install time half-way through.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Three stories | US1 is the path the other two alert through and is provable with no systemd at all; US2 and US3 both install units but their failure modes differ entirely — a leaked process tree versus a discarded workflow history. |
| Generating units rather than shipping static files | Static files cannot name the operator's install path, their Temporal binary, or their runtime root. Trap 7 is the whole reason this is code. |
| Reaping at all, when systemd contains the slice | Containment stops a leak from killing the host; it does not stop the leak. The orphans reparent to PID 1 and stay inside the cgroup, accruing until the slice's own limit is hit. Nothing else in the system will ever kill them. |
| An out-of-band alert path parallel to 041's workflow | The alert that says Temporal is down cannot be hosted by Temporal. This is one small module precisely so the exception stays visible rather than becoming a second escalation system. |

## Verification

`uv run pytest -q` green in the worktree before and after each story.

Green is necessary and badly insufficient here — most of what this epic claims
is about a host, and a unit test cannot see a host. Four claims need measured
evidence pasted into the diff:

- **SC-002**: process count before and after stopping a unit with children.
- **SC-003**: a seeded orphan population reaped, with the three-condition
  discrimination of trap 3 shown.
- **SC-004**: workflow history surviving a managed-unit restart.
- **SC-006**: the generated unit text, scanned, containing no path outside the
  operator's installation.

And SC-001 — an alert delivered *while Temporal is still down* — is the one this
epic exists for. It is measured, not assumed. If you cannot measure it in your
environment, say so plainly rather than asserting it.
