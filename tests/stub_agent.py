#!/usr/bin/env python3
"""An executable standing in for the agent CLI, and the helpers that drive it.

The adapter is the one place the factory touches an agent (D-018), and every
property US2 asserts about it is only observable *from inside the child*: which
environment variables survived the allowlist, which directory the agent ran in,
what arrived on stdin, whether SIGTERM reached the whole process group. A fake
adapter would assert none of that, so this module is a real program that the
adapter really launches — `claude` with everything interesting replaced by
bookkeeping.

Three constraints shape it, all of them consequences of contracts/adapter.md:

- **It is launched with a scrubbed environment**, so it cannot be configured
  through one. The child env is exactly `ANTHROPIC_BASE_URL`,
  `ANTHROPIC_AUTH_TOKEN`, `PATH`, `HOME`, `LANG`, `TERM` — a `STUB_AGENT_CONTROL`
  variable would either be smuggled past the allowlist (making the exactness test
  a lie) or force the adapter to know about the stub. `HOME` is the one
  test-controlled *location* in that list, so the control file lives at
  `$HOME/stub-agent-control.json` — the same fake home the session transcript is
  written under.
- **It runs with no `PYTHONPATH` and no virtualenv**, so it imports nothing but
  the standard library and nothing from this repository. The module is therefore
  importable by tests *and* directly executable (`#!/usr/bin/env python3`,
  mode 0755); `install_as()` exists for tests that would rather shim it onto
  `PATH` as `claude` than name its path.
- **It is launched more than once in the same worktree** (a retry, and the
  reap-before-relaunch case of research R4), so records never overwrite: each
  launch claims its own `.stub-agent/<n>/` directory and the sequence is the
  order the launches happened in.

Behaviour is scripted, never inferred. An unconfigured stub exits 0 having
written a transcript — the happy path — and every other outcome is a control-file
field, because a stub that decided for itself when to fail would agree with the
adapter about what failure looks like, which is exactly what the classification
tests must not assume.

The control fields exist one per assertion the adapter contract calls for:
`exit_code` (exit 0 → COMPLETED vs non-zero → AGENT_ERROR), `sleep_s` (a run that
outlives its deadline, US2-S3), `ignore_sigterm` (a run that only SIGKILL ends,
so TERM→KILL escalation is observable rather than assumed — the
`hang-ignoring-sigterm.sh` gate fixture's trick), `spawn_child` (a grandchild
that only a *process-group* signal reaches, so `os.killpg` is distinguishable
from killing one pid), `write_transcript` (the session file the archive step
copies — and its absence, which must still archive `stdout.log`, FR-007), and
`stdout`/`stderr` (content to find in the archived log).

The transcript is written *before* the sleep and appended to after it, so a run
killed at its deadline leaves a partial transcript on disk — archiving on every
path (FR-007) is testable precisely because the killed path has something to
archive.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: This file, as the adapter's `claude` binary.
STUB_AGENT_PATH = Path(__file__).resolve()

#: Read from the *claimed* `$HOME` — the only writable location the env
#: allowlist hands the child (contracts/adapter.md § Environment).
CONTROL_FILENAME = "stub-agent-control.json"

#: One directory per launch beneath the worktree, numbered from 1.
RECORD_DIRNAME = ".stub-agent"

ARGV_FILE = "argv.json"
ENV_FILE = "env.json"
CWD_FILE = "cwd.txt"
STDIN_FILE = "stdin.txt"
PROCESS_FILE = "process.json"
SIGNALS_FILE = "signals.log"

#: Always printed, so `stdout.log` has an assertable line even when a test
#: scripts no output of its own.
BANNER = "stub-agent: launched"

#: Appended after a clean run, so a transcript archived from a killed attempt is
#: distinguishable from a completed one by line count alone.
TRANSCRIPT_START = "start"
TRANSCRIPT_END = "end"

_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")


# --- the session transcript's location ---------------------------------------


def project_dir_name(cwd: Path | str) -> str:
    """Claude Code's per-cwd transcript directory name: every non-alphanumeric
    character of the absolute path replaced by `-` (`/home/a/b` →
    `-home-a-b`).

    The adapter has to reproduce this to find the file it archives (R6), so the
    rule lives here, in the stand-in for the program that defines it, and the
    Tier 1 smoke (T032) is what proves the rule still matches the real CLI.
    """
    return _NON_ALNUM.sub("-", str(Path(cwd).resolve()))


def session_transcript_path(home: Path | str, cwd: Path | str, session_id: str) -> Path:
    """`$HOME/.claude/projects/<munged cwd>/<session id>.jsonl`."""
    return Path(home) / ".claude" / "projects" / project_dir_name(cwd) / f"{session_id}.jsonl"


# --- scripting the stub -------------------------------------------------------


@dataclass(frozen=True)
class Control:
    """What the stub does this launch. Defaults are the happy path."""

    exit_code: int = 0
    sleep_s: float = 0.0
    write_transcript: bool = True
    stdout: str = ""
    stderr: str = ""
    ignore_sigterm: bool = False
    spawn_child: bool = False
    child_sleep_s: float = 300.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "sleep_s": self.sleep_s,
            "write_transcript": self.write_transcript,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ignore_sigterm": self.ignore_sigterm,
            "spawn_child": self.spawn_child,
            "child_sleep_s": self.child_sleep_s,
        }


def write_control(home: Path | str, **overrides: Any) -> Path:
    """Script the next launch under `home`; returns the control file's path.

    Unknown fields are a `TypeError` from `Control(**overrides)` rather than a
    silently ignored key — a typo in a test's script would otherwise look like
    the stub disobeying it.
    """
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / CONTROL_FILENAME
    path.write_text(json.dumps(Control(**overrides).as_dict(), indent=2), encoding="utf-8")
    return path


def load_control(home: Path | str) -> Control:
    """The scripted behaviour, or the happy-path default when nothing is scripted."""
    path = Path(home) / CONTROL_FILENAME
    if not path.exists():
        return Control()
    return Control(**json.loads(path.read_text(encoding="utf-8")))


def install_as(bin_dir: Path | str, name: str = "claude") -> Path:
    """Symlink the stub into `bin_dir` as `name`, for tests that shim `PATH`."""
    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / name
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(STUB_AGENT_PATH)
    return link


# --- reading what the stub recorded -------------------------------------------


def flag_value(argv: list[str], name: str) -> str | None:
    """The value following `name` in `argv`, tolerating `--flag=value`."""
    for index, item in enumerate(argv):
        if item == name:
            return argv[index + 1] if index + 1 < len(argv) else None
        if item.startswith(f"{name}="):
            return item.split("=", 1)[1]
    return None


@dataclass(frozen=True)
class Invocation:
    """One launch, as recorded from inside the child."""

    sequence: int
    directory: Path
    argv: list[str]
    env: dict[str, str]
    cwd: str
    stdin: str
    pid: int
    pgid: int
    child_pid: int | None = None

    def flag(self, name: str) -> str | None:
        """The value following `name` in argv (`--model` → the alias), or None."""
        return flag_value(self.argv, name)

    @property
    def signals(self) -> list[str]:
        """Signals delivered to this launch, `"TERM +12.004s"`, in arrival order.

        Read on access rather than captured at construction: a test may read the
        record while the process is still being terminated.
        """
        log = self.directory / SIGNALS_FILE
        if not log.exists():
            return []
        return log.read_text(encoding="utf-8").split("\n")[:-1]


def invocations(cwd: Path | str) -> list[Invocation]:
    """Every launch recorded in `cwd`, in launch order."""
    root = Path(cwd) / RECORD_DIRNAME
    if not root.is_dir():
        return []
    found: list[Invocation] = []
    for directory in sorted(root.iterdir(), key=lambda item: int(item.name)):
        argv_file = directory / ARGV_FILE
        if not argv_file.exists():
            continue
        process = json.loads((directory / PROCESS_FILE).read_text(encoding="utf-8"))
        found.append(
            Invocation(
                sequence=int(directory.name),
                directory=directory,
                argv=json.loads(argv_file.read_text(encoding="utf-8")),
                env=json.loads((directory / ENV_FILE).read_text(encoding="utf-8")),
                cwd=(directory / CWD_FILE).read_text(encoding="utf-8"),
                stdin=(directory / STDIN_FILE).read_text(encoding="utf-8"),
                pid=process["pid"],
                pgid=process["pgid"],
                child_pid=process.get("child_pid"),
            )
        )
    return found


def last_invocation(cwd: Path | str) -> Invocation:
    """The most recent launch in `cwd`; raises if the stub never ran there."""
    found = invocations(cwd)
    if not found:
        raise LookupError(f"the stub agent never ran in {cwd} (no {RECORD_DIRNAME}/ records)")
    return found[-1]


# --- the program itself -------------------------------------------------------


@dataclass
class _Recorder:
    """The launch's own record directory, claimed exclusively."""

    directory: Path
    started: float = field(default_factory=time.monotonic)

    def write(self, name: str, text: str) -> None:
        (self.directory / name).write_text(text, encoding="utf-8")

    def append(self, name: str, line: str) -> None:
        with (self.directory / name).open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
            handle.flush()

    def signal(self, name: str) -> None:
        self.append(SIGNALS_FILE, f"{name} +{time.monotonic() - self.started:.3f}s")


def _claim_record_dir(cwd: Path) -> _Recorder:
    """The lowest unused `.stub-agent/<n>/`, created exclusively.

    Exclusive creation rather than "count what is there and add one" because the
    reaping case (R4) has two stubs alive in one worktree at once, and two
    launches sharing a record directory would report one of them as the other.
    """
    root = cwd / RECORD_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    sequence = 1
    while True:
        directory = root / str(sequence)
        try:
            directory.mkdir()
        except FileExistsError:
            sequence += 1
            continue
        return _Recorder(directory=directory)


def _read_stdin() -> str:
    """The prompt, verbatim. A tty means nobody piped one (a hand-run stub)."""
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _write_transcript(home: Path, cwd: Path, session_id: str | None, event: str) -> None:
    """Append one Claude-Code-shaped record to the session transcript.

    Without `--session-id` there is no file to name, so nothing is written: the
    adapter's contract is that *it* generates the id (R6), and a stub that
    invented one anyway would hide a missing flag behind a transcript that
    appeared regardless.
    """
    if not session_id:
        return
    path = session_transcript_path(home, cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "stub-agent",
                    "event": event,
                    "sessionId": session_id,
                    "cwd": str(cwd),
                }
            )
            + "\n"
        )


def _spawn_child(sleep_s: float) -> int:
    """A grandchild in the stub's process group, so group termination is visible.

    No `start_new_session`: the point of this process is that only a signal sent
    to the *group* reaches it (contracts/adapter.md § Monitor).
    """
    child = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({sleep_s!r})"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return child.pid


def main(argv: list[str]) -> int:
    """`argv` is `sys.argv` whole — argv[0] included, as the child received it."""
    cwd = Path.cwd()
    home = Path(os.environ.get("HOME") or cwd)
    control = load_control(home)
    recorder = _claim_record_dir(cwd)

    session_id = flag_value(argv, "--session-id")

    child_pid = _spawn_child(control.child_sleep_s) if control.spawn_child else None

    recorder.write(ARGV_FILE, json.dumps(list(argv), indent=2))
    recorder.write(ENV_FILE, json.dumps(dict(os.environ), indent=2, sort_keys=True))
    recorder.write(CWD_FILE, str(cwd))
    recorder.write(
        PROCESS_FILE,
        json.dumps(
            {"pid": os.getpid(), "pgid": os.getpgid(0), "child_pid": child_pid}, indent=2
        ),
    )
    # Last, and only once stdin is drained: a test polling for "the stub is up"
    # waits on the file that proves the prompt arrived.
    recorder.write(STDIN_FILE, _read_stdin())

    def on_term(signum: int, _frame: Any) -> None:
        recorder.signal(signal.Signals(signum).name.removeprefix("SIG"))
        if not control.ignore_sigterm:
            sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, on_term)

    print(BANNER, flush=True)
    if control.stdout:
        print(control.stdout, flush=True)
    if control.stderr:
        print(control.stderr, file=sys.stderr, flush=True)

    if control.write_transcript:
        _write_transcript(home, cwd, session_id, TRANSCRIPT_START)

    if control.sleep_s:
        time.sleep(control.sleep_s)

    if control.write_transcript:
        _write_transcript(home, cwd, session_id, TRANSCRIPT_END)

    return control.exit_code


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    sys.exit(main(sys.argv))
