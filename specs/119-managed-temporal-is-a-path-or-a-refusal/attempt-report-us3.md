# Attempt 1 — US3: the server can start, and verification proves it

## T024 — the operator's demonstration

The plan's § *Verification the operator will run* asks for a fresh host
declaring managed mode: `ergane install --from-file`, `ergane worker install`,
`systemctl --user status` on the three units, and `ergane install --verify` with
the server up and again with it deliberately stopped.

**The substitution, and it is the first thing to state.** This attempt runs in a
bwrap sandbox with no systemd user session — `systemctl --user` cannot reach a
bus at all — and the host outside it is the operator's own floor, where
`ergane-worker@*.service` and `ergane-bridge.service` are the running factory
and `127.0.0.1:7233` is its Temporal. Enabling units of those names, or binding
that port, would have taken the factory down to produce a screenshot. So the
systemd half is **not** run, and what replaces it is stated at each step: the
units are generated through the same `declared_layout` → `generated_files` path
the verb runs, and the Temporal unit's own `ExecStart` line is executed exactly
as systemd would execute it, with `--port 17233` appended because 7233 is
occupied by the operator's server. Everything below is pasted tool output.

Both `--verify` runs are real, against a real dev server, and they disagree —
which is the whole point of the story.

### 1. The declaration, and the two refusals that stand in for the systemd half

```text
$ uv run ergane install --from-file /tmp/us3-demo2/answers.toml   # mode = "managed"
ergane: temporal.mode = "managed" requires a systemd user session; this host does not have one (systemctl --user is not available). Choose external Temporal or enable user sessions.
applied default: llm.gateway_mode = "external"
EXIT=1

$ uv run ergane worker install
ergane: no systemd user session is available (systemctl --user cannot connect to the bus); this usually means the command is running inside a container, where systemd user units are not available. Use the container supervisor to manage the worker instead of this verb.
EXIT=1

$ systemctl --user status ergane-temporal.service ergane-worker@.service ergane-bridge.service
Failed to connect to bus: No medium found
EXIT=1
```

Both refusals are the correct behaviour for this environment (042-US3 T025 and
FR-015), and together they are why no unit state can be pasted here. The config
was then written to the same path by hand, declaring `mode = "managed"`.

### 2. The units the verb would have written

```text
$ python - <<'PY'   # declared_layout(unit_dir=…) -> generated_files -> write
temporal_mode = managed
wrote /tmp/us3-demo2/units/ergane.slice
wrote /tmp/us3-demo2/units/ergane-worker@.service
wrote /tmp/us3-demo2/units/ergane-bridge.service
wrote /tmp/us3-demo2/units/ergane-temporal.service
wrote /tmp/us3-demo2/units/ergane-probe.service
wrote /tmp/us3-demo2/units/ergane-probe.timer
wrote /tmp/us3-demo2/state/ergane/supervision/ergane-run.sh

$ grep -n 'Wants=\|After=' units/ergane-bridge.service units/ergane-worker@.service
units/ergane-worker@.service:14:Wants=ergane-temporal.service
units/ergane-worker@.service:15:After=ergane-temporal.service
units/ergane-bridge.service:14:Wants=ergane-temporal.service
units/ergane-bridge.service:15:After=ergane-temporal.service

$ ls /tmp/us3-demo2/state/ergane/    # no database directory yet
supervision
```

US3-S2 (FR-008) on disk: the server unit is generated because the declared mode
reached the layout, and both services carry both directives.

### 3. The unit's own command line, before and after

The generated `ExecStart` was run verbatim. This is the step that found a defect
the gate could not: US2 fixed the wrapper and proved it with a hand-written
argument list, but the *unit* still passed its flags immediately after the module
name, where the wrapper's second positional is the working directory.

```text
$ ergane-run.sh factory.supervision.temporal_server --db-filename …/dev.db --namespace ergane --log-level warn
/tmp/us3-demo2/state/ergane/supervision/ergane-run.sh: 19: cd: Illegal option --
EXIT=2
```

With the unit spelling out the two positionals it does not mean to override:

```text
$ ergane-run.sh factory.supervision.temporal_server <install_root> <interpreter> \
>     --db-filename /tmp/us3-demo2/state/ergane/temporal/dev.db --namespace ergane --log-level warn --port 17233 &
INFO:root:starting managed Temporal dev server on 127.0.0.1:17233 (db=/tmp/us3-demo2/state/ergane/temporal/dev.db)
Temporal CLI 1.8.2 (Server 1.31.2, UI 2.50.1)

Temporal Server:      localhost:17233
Temporal Persistence: /tmp/us3-demo2/state/ergane/temporal/dev.db
Temporal Metrics:     http://localhost:36503/metrics

$ ls /tmp/us3-demo2/state/ergane/temporal/    # created by the process that named it
dev.db

$ ss -ltn | grep 17233
LISTEN 0      4096       127.0.0.1:17233      0.0.0.0:*

$ ps -eo pid,args | grep temporal_server
  27767 …/.venv/bin/python3 -m factory.supervision.temporal_server --db-filename /tmp/us3-demo2/state/ergane/temporal/dev.db --namespace ergane --log-level warn --port 17233
```

Three things in that argv at once: the flags arrived (US2's FR-005 through a
generated unit rather than a fixture), the database directory the `ls` above
showed absent now exists (US3-S1 / FR-007), and the command line contains
`python3 -m` rather than `python -m`, so the 2026-08-12 sweep still would not
match it.

### 4. `--verify`, both ways

Server up:

```text
$ uv run ergane install --verify
[PASS] temporal: Temporal at 127.0.0.1:17233 has namespace `ergane`
```

Same config, same command, server deliberately stopped:

```text
$ kill <server>; ss -ltn | grep 17233
(nothing listening on 127.0.0.1:17233)

$ uv run ergane install --verify
[FAIL] temporal: Temporal at 127.0.0.1:17233 did not answer: RuntimeError: Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:17233, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" }))); this installation declares managed Temporal, so the server is this engine's own ergane-temporal.service — `systemctl --user status ergane-temporal.service` says why it is not answering
```

That is what the spec is buying. Before this story the same two runs both printed
`[PASS] temporal: managed Temporal: the engine installs and supervises the
server; uptime is verified by the supervision probe`, with nothing dialled and
nothing running.

## What the demonstration could not show, and what would show it

No unit state, no `systemctl --user status`, no boot ordering observed: they need
a host with a systemd user session that is not the operator's own floor. The
three claims that remain unwitnessed on real systemd are that the ordering
directives keep worker and bridge inside their start limit across a boot, that
`InstallReport.states` prints what `systemctl is-active` prints for a genuinely
failed unit, and that `ergane worker uninstall` removes units on a host whose
Temporal is down. Each is covered by a committed test against the command seam
(`tests/test_119_the_server_starts_and_verify_proves_it.py`), and the first is
the one an operator should re-run first on a real managed host.
