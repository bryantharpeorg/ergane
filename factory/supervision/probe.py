"""042-US4: the probe — what it sees, what it says, and what it will not do.

It runs from a timer, outside the slice it watches, and it is the process that
has to work when Temporal is the thing that died. So it imports no client, and
it raises everything it has to say through US1's out-of-band path.

Three properties are the whole design:

- **It reports; it does not remediate (FR-014).** The instinct on reading "the
  worker is down" is to restart it. systemd owns restarts, and a restart into
  an already-dying host deepens an OOM storm rather than ending it. Reaping
  orphaned test servers is the sole exception, and only because nothing else
  ever will: a server whose parent died is reparented to PID 1, the fixtures'
  `finally` never runs after a SIGKILL, and it accrues at ~66 MiB a copy until
  the host dies — 2026-08-11, 8,131 copies, 123 GiB, one dead host.
- **Alerts are edge-triggered, with a heartbeat under them (FR-013).** The
  timer fires every couple of minutes, and a page per firing is a channel the
  operator mutes within a day — worse than none, because it still looks
  supervised. One message per status change, plus a heartbeat on its own much
  longer interval, so silence stays distinguishable from a dead probe.
- **It is loud when it cannot escalate (FR-015).** A probe whose alert went
  nowhere is indistinguishable from a healthy floor, the exact failure this
  unit exists to end — so it says so on stderr and exits 2, outside the
  `SuccessExitStatus=0 1` its unit declares.

One deliberate divergence from the prior art, which pages on every reap: here a
reap below the configured threshold is a note, and only a count at or above it
pages (US4-S1). A leak producing two orphans an hour would otherwise page every
two minutes, which is the muting FR-013 forbids.
"""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from factory.supervision.alert import AlertOutcome, StackAlert, send_alert
from factory.supervision.units import (
    BRIDGE_UNIT,
    LEGACY_WORKER_UNIT,
    SLICE_UNIT,
    TEMPORAL_UNIT,
    CommandResult,
    _run_command,
    supervision_home,
)

HEALTHY = "healthy"
DEGRADED = "degraded"

#: What the whole-stack messages name as their subject.
STACK = "ergane stack"

#: `ps` reports `comm` truncated to 15 characters, so the leaked servers appear
#: as this and never as `temporal-test-server`. Matching the full name matches
#: nothing, forever, silently — which is a safety net that reports a healthy
#: floor while the host fills up.
ORPHAN_COMM_PREFIX = "temporal-test-s"

#: The probe's state, in one file: the last status, when it last changed, and
#: when the last heartbeat went out.
STATE_FILE = "probe.json"


@dataclasses.dataclass(frozen=True)
class ProbeConfig:
    """The thresholds, and the units this installation supervises."""

    #: 082-US4 renamed the worker unit this watches to what it now is — the
    #: legacy one. What it does NOT do is change which units are watched: a
    #: host that has migrated off it runs versioned instances instead, and
    #: naming them is a resolution against the deployments directory
    #: (`units.deployed_instances`) rather than a constant. That belongs with
    #: whoever owns this file's sweep, not to the story that retired the name.
    units: tuple[str, ...] = (LEGACY_WORKER_UNIT, BRIDGE_UNIT, TEMPORAL_UNIT)
    slice_unit: str = SLICE_UNIT
    dial: tuple[tuple[str, int], ...] = ()
    mem_warn_gib: int = 16
    mem_crit_gib: int = 8
    #: Grace, so a fresh spawn is never raced: reaping a two-second-old server
    #: kills a test that was working.
    orphan_min_age_s: int = 120
    orphan_alert_at: int = 10
    heartbeat_every_s: int = 86_400


@dataclasses.dataclass(frozen=True)
class Host:
    """Everything the probe reads about the machine, behind one seam."""

    systemctl: Callable[[Sequence[str]], CommandResult]
    process_table: Callable[[], str]
    meminfo: Callable[[], str]
    uptime_s: Callable[[], float]
    kill: Callable[[int], None]
    dial: Callable[[str, int], bool]


def real_host() -> Host:
    """The production readings. Resolved at call time so a test can refuse them."""
    return Host(
        systemctl=_run_command,
        process_table=_read_process_table,
        meminfo=lambda: Path("/proc/meminfo").read_text(encoding="utf-8"),
        uptime_s=_uptime_s,
        kill=lambda pid: _kill(pid),
        dial=_dial,
    )


@dataclasses.dataclass(frozen=True)
class ProcessRow:
    """One line of `ps -eo pid=,ppid=,etimes=,comm=`."""

    pid: int
    ppid: int
    age_s: int
    comm: str


def parse_process_table(text: str) -> tuple[ProcessRow, ...]:
    rows: list[ProcessRow] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        rows.append(
            ProcessRow(int(parts[0]), int(parts[1]), int(parts[2]), parts[3])
        )
    return tuple(rows)


def orphaned_test_servers(
    rows: Sequence[ProcessRow], *, min_age_s: int = 120
) -> tuple[ProcessRow, ...]:
    """The three conditions, and each one is why the other two are not enough.

    The truncated name, because `comm` is 15 characters. `ppid == 1`, because a
    test server with a live parent is a running test rather than a leak. And
    the age, because a fresh spawn is mid-fork and reaping it breaks the test
    that was working. Drop any one and the net becomes a saboteur.
    """
    return tuple(
        row
        for row in rows
        if row.comm.startswith(ORPHAN_COMM_PREFIX)
        and row.ppid == 1
        and row.age_s > min_age_s
    )


def reap_orphans(
    rows: Sequence[ProcessRow], *, kill: Callable[[int], None] | None = None
) -> int:
    """Kill each orphan and count what actually died.

    The one thing this probe does that systemd cannot, and the one place in the
    module that signals anything (FR-014). An orphan that exited between the
    read and the kill is the normal case on a busy host, not an error.
    """
    reaped = 0
    for row in rows:
        try:
            if kill is None:
                _kill(row.pid)
            else:
                kill(row.pid)
        except OSError:
            continue
        reaped += 1
    return reaped


@dataclasses.dataclass(frozen=True)
class UnitReading:
    """Whether a unit is up, and how long it has been down if it is not."""

    name: str
    active: bool
    down_for_s: float


def read_unit(name: str, host: Host) -> UnitReading:
    """Ask systemd, and take the outage duration from systemd's own clock.

    `InactiveEnterTimestampMonotonic` is microseconds since boot, which is why
    the host's uptime is the other half of the subtraction: an outage measured
    against a state file would restart every time the probe's own state was
    lost, and the state file is on the disk of the host that is failing.
    """
    answer = host.systemctl(
        (
            "systemctl",
            "--user",
            "show",
            name,
            "-p",
            "ActiveState",
            "-p",
            "InactiveEnterTimestampMonotonic",
            "--value",
        )
    )
    lines = [line.strip() for line in answer.out.splitlines()]
    active = bool(lines) and lines[0] == "active"
    since_us = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0
    down_for = 0.0
    if not active and since_us:
        down_for = max(0.0, host.uptime_s() - since_us / 1_000_000)
    return UnitReading(name, active, down_for)


@dataclasses.dataclass(frozen=True)
class Verdict:
    """One pass over the machine: what is wrong, what was noted, who to name."""

    status: str
    problems: tuple[str, ...]
    notes: tuple[str, ...]
    reaped: int
    subject: str
    subject_duration_s: float

    @property
    def detail(self) -> str:
        body = "; ".join(self.problems) if self.problems else "all units up"
        if self.notes:
            body = f"{body} ({', '.join(self.notes)})"
        return body


def assess(config: ProbeConfig, host: Host) -> Verdict:
    """Read the machine once and render a verdict.

    Liveness alone was never the gap: on 2026-08-11 every unit was active while
    the host ran out of memory. Headroom and orphan count are why this checks
    more than `is-active`.
    """
    problems: list[str] = []
    notes: list[str] = []

    readings = [read_unit(name, host) for name in config.units]
    down = [reading for reading in readings if not reading.active]
    problems += [f"{reading.name} not active" for reading in down]

    available = _available_gib(host.meminfo())
    if available is not None and available < config.mem_crit_gib:
        problems.append(f"host memory CRITICAL: {available} GiB available")
    elif available is not None and available < config.mem_warn_gib:
        problems.append(f"host memory low: {available} GiB available")

    for address, port in config.dial:
        if not host.dial(address, port):
            problems.append(f"{address}:{port} unreachable")

    orphans = orphaned_test_servers(
        parse_process_table(host.process_table()), min_age_s=config.orphan_min_age_s
    )
    reaped = reap_orphans(orphans, kill=host.kill)
    if reaped:
        notes.append(f"reaped {reaped} orphaned test server(s)")
    if len(orphans) >= config.orphan_alert_at:
        problems.append(f"test-server leak: {len(orphans)} orphaned test servers")

    used = host.systemctl(
        ("systemctl", "--user", "show", config.slice_unit, "-p", "MemoryCurrent", "--value")
    ).out.strip()
    if used.isdigit():
        notes.append(f"{config.slice_unit} {int(used) // 1_073_741_824} GiB")

    return Verdict(
        status=DEGRADED if problems else HEALTHY,
        problems=tuple(problems),
        notes=tuple(notes),
        reaped=reaped,
        subject=down[0].name if down else STACK,
        subject_duration_s=down[0].down_for_s if down else 0.0,
    )


@dataclasses.dataclass(frozen=True)
class ProbeState:
    """What the last run left behind, so this one can tell what changed."""

    status: str | None
    changed_at: float
    heartbeat_at: float


def read_state(state_dir: Path) -> ProbeState:
    """The previous run's state, or none at all.

    An unreadable file reads as no state rather than raising: a truncated write
    during an OOM is exactly the condition the next run exists to report.
    """
    try:
        document = json.loads((Path(state_dir) / STATE_FILE).read_text(encoding="utf-8"))
        return ProbeState(
            status=document.get("status"),
            changed_at=float(document.get("changed_at", 0.0)),
            heartbeat_at=float(document.get("heartbeat_at", 0.0)),
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return ProbeState(None, 0.0, 0.0)


def write_state(state_dir: Path, state: ProbeState) -> None:
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / STATE_FILE).write_text(
        json.dumps(dataclasses.asdict(state)), encoding="utf-8"
    )


@dataclasses.dataclass(frozen=True)
class AlertDecision:
    """Whether to page, and whether paging restarts the heartbeat clock."""

    alert: StackAlert | None
    heartbeat: bool


def decide_alert(
    verdict: Verdict, state: ProbeState, *, now: float, heartbeat_every_s: int
) -> AlertDecision:
    """The edge-trigger table (FR-013), and it is deliberately small.

    A first observation of *healthy* is silent: there is no incident behind it,
    and a fresh install that opens with "RECOVERED" teaches the operator that
    the channel is noisy. A first observation of *degraded* pages, because that
    one is real.
    """
    if verdict.status == DEGRADED and state.status != DEGRADED:
        return AlertDecision(
            StackAlert(verdict.subject, verdict.detail, verdict.subject_duration_s),
            False,
        )
    if verdict.status == HEALTHY and state.status == DEGRADED:
        return AlertDecision(
            StackAlert(
                STACK, f"recovered — {verdict.detail}", max(0.0, now - state.changed_at)
            ),
            False,
        )
    if (
        verdict.status == HEALTHY
        and state.status == HEALTHY
        and now - state.heartbeat_at >= heartbeat_every_s
    ):
        return AlertDecision(
            StackAlert(STACK, f"healthy — {verdict.detail}", now - state.heartbeat_at),
            True,
        )
    return AlertDecision(None, False)


@dataclasses.dataclass(frozen=True)
class ProbeRun:
    """One firing of the timer, whole."""

    verdict: Verdict
    alert: StackAlert | None
    outcome: AlertOutcome | None
    exit_code: int


def run_probe(
    config: ProbeConfig,
    host: Host,
    state_dir: Path,
    *,
    now: float | None = None,
    alert: Callable[[StackAlert], AlertOutcome] = send_alert,
) -> ProbeRun:
    """Read the machine, decide, page if the edge says so, and record.

    `alert` defaults to US1's synchronous door — the path that works when
    Temporal is gone — and is injectable only so a test can assert the decision
    without a transport.
    """
    moment = time.time() if now is None else now
    verdict = assess(config, host)
    state = read_state(state_dir)
    decision = decide_alert(
        verdict, state, now=moment, heartbeat_every_s=config.heartbeat_every_s
    )
    outcome = alert(decision.alert) if decision.alert is not None else None

    became_healthy = verdict.status == HEALTHY and state.status != HEALTHY
    write_state(
        state_dir,
        ProbeState(
            status=verdict.status,
            changed_at=moment if verdict.status != state.status else state.changed_at,
            heartbeat_at=(
                moment if decision.heartbeat or became_healthy else state.heartbeat_at
            ),
        ),
    )

    print(f"{verdict.status}: {verdict.detail}", file=sys.stdout, flush=True)
    if outcome is not None and not outcome.delivered:
        # The same words US1 logs, on purpose: one phrase an operator greps the
        # journal for, and the timer's failure mail carries this half.
        print(
            f"WARN: cannot escalate ({outcome.failure}): {outcome.text}",
            file=sys.stderr,
            flush=True,
        )
        return ProbeRun(verdict, decision.alert, outcome, 2)
    return ProbeRun(
        verdict, decision.alert, outcome, 0 if verdict.status == HEALTHY else 1
    )


def _available_gib(meminfo: str) -> int | None:
    for line in meminfo.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                return int(parts[1]) // 1_048_576
    return None


def _read_process_table() -> str:
    return _run_command(("ps", "-eo", "pid=,ppid=,etimes=,comm=")).out


def _uptime_s() -> float:
    return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])


def _dial(address: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(3.0)
        return probe.connect_ex((address, port)) == 0


def _kill(pid: int) -> None:
    os.kill(pid, signal.SIGKILL)


def _default_dial() -> tuple[tuple[str, int], ...]:
    """The declared Temporal address, if one resolves.

    Imported here rather than at module scope, and swallowed rather than
    raised: a probe that cannot parse a config has stopped supervising, and the
    reachability check is the least of what it reports.
    """
    try:
        from factory.controlplane.resolve import resolve_temporal_target

        address, _, port = resolve_temporal_target().address.rpartition(":")
        return ((address or "127.0.0.1", int(port)),)
    except Exception:
        return ()


def main(argv: Sequence[str] | None = None) -> int:
    """`python3 -m factory.supervision.probe` — what the timer runs."""
    run = run_probe(ProbeConfig(dial=_default_dial()), real_host(), supervision_home())
    return run.exit_code


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
