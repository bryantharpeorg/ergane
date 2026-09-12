#!/usr/bin/env python3
"""An executable standing in for the Codex CLI, and the helpers that drive it.

`tests/stub_agent.py` stands in for `claude`; this one stands in for `codex`.
What a second adapter asserts about its own launches is only observable from
inside the child — the argv, the env, what arrived on stdin — so the stand-in
is a real program the adapter really launches. It records the same five facts
`stub_agent.py` records into `.stub-codex/<n>/` under the worktree, and honours
a control file at `$HOME/stub-codex-control.json` (the claimed per-node `HOME`
is again the one test-controlled location in the child env), with the shape
the Codex probe measured (2026-09-08, `@openai/codex@0.153.4`): the refusal is
on stderr with exit 1 — the inverse of the Claude stub, so `stderr` is a
control field; a turn leaves a rollout file under `$CODEX_HOME/sessions/`
named after an id the CLI generated itself, which the adapter finds without
ever having supplied one; and the stub reads no `config.toml` — the *adapter*
writes it, and the config tests read the generated file directly.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: This file, as the adapter's `codex` binary.
STUB_CODEX_PATH = Path(__file__).resolve()

#: Read from the claimed per-node HOME — the one test-controlled location in
#: the child env (the same trick `stub_agent.py` uses, for the same reason).
CONTROL_FILENAME = "stub-codex-control.json"

#: One directory per launch beneath the worktree, numbered from 1. Never
#: `.stub-agent/`: the two stubs may record into one worktree, and the
#: sequences must not collide.
RECORD_DIRNAME = ".stub-codex"

ARGV_FILE = "argv.json"
ENV_FILE = "env.json"
CWD_FILE = "cwd.txt"
STDIN_FILE = "stdin.txt"
PROCESS_FILE = "process.json"

#: The gateway key's env name, re-exported so test and adapter cannot
#: disagree about the spelling.
CODEX_GATEWAY_KEY = "CODEX_GATEWAY_KEY"

#: The env var naming the per-node CODEX_HOME the adapter seeds. The CLI reads
#: it directly (measured 2026-09-08: sessions land under it, not `$HOME/.codex`).
CODEX_HOME_ENV = "CODEX_HOME"

#: Appended to the rollout directory tree the stub writes when a turn ran.
ROLLOUT_DIRNAME = "sessions"

#: Always printed, so `stdout.log` has an assertable line even when a test
#: scripts no output of its own.
BANNER = "stub-codex: launched"

#: The refusal the real CLI prints (measured) — the stub prints it when the
#: control file scripts a refusal, so the classifier tests replay the shape
#: rather than the exact bytes of a live proxy error.
REFUSAL_MARKER = "unexpected status 401 Unauthorized"


@dataclass(frozen=True)
class Control:
    """What the stub does this launch. Defaults are the happy path."""

    exit_code: int = 0
    sleep_s: float = 0.0
    #: A turn happened: write the rollout file under `$CODEX_HOME/sessions/`.
    write_rollout: bool = True
    stdout: str = ""
    stderr: str = ""
    rollout_text: str | None = None
    interleave_stderr: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "sleep_s": self.sleep_s,
            "write_rollout": self.write_rollout,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "rollout_text": self.rollout_text,
            "interleave_stderr": self.interleave_stderr,
        }


def write_control(home: Path | str, **overrides: Any) -> Path:
    """Script the next launch under `home`; returns the control file's path."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / CONTROL_FILENAME
    path.write_text(json.dumps(Control(**overrides).as_dict(), indent=2), encoding="utf-8")
    return path


def install_as(bin_dir: Path | str, name: str = "codex") -> Path:
    """Symlink the stub into `bin_dir` as `codex`, for tests that shim `PATH`."""
    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / name
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(STUB_CODEX_PATH)
    return link


def codex_home(home_path: Path | str) -> Path:
    """The per-node CODEX_HOME the adapter seeds: `<home>/.codex`."""
    return Path(home_path) / ".codex"


def rollout_path(codex_home: Path | str, session_id: str) -> Path:
    """Where a turn's rollout file lands, as the measured CLI writes it.

    `$CODEX_HOME/sessions/<YYYY>/<MM>/<DD>/rollout-…-<id>.jsonl`. The adapter
    must find the tree without having supplied an id (the probe is the tree,
    not one name); the test wants the exact file it scripted, so the id is
    spelled out here.
    """
    return (
        Path(codex_home)
        / ROLLOUT_DIRNAME
        / "2026"
        / "09"
        / "08"
        / f"rollout-2026-09-08T00-00-00-{session_id}.jsonl"
    )


def flag_value(argv: list[str], name: str) -> str | None:
    """The value following `name` in `argv`, tolerating `--flag=value`."""
    for index, item in enumerate(argv):
        if item == name:
            return argv[index + 1] if index + 1 < len(argv) else None
        if item.startswith(f"{name}="):
            return item.split("=", 1)[1]
    return None


def last_invocation(cwd: Path | str) -> dict[str, Any]:
    """The most recent launch's record; raises if the stub never ran there."""
    root = Path(cwd) / RECORD_DIRNAME
    directories = sorted(root.iterdir(), key=lambda item: int(item.name)) if root.is_dir() else []
    if not directories:
        raise LookupError(f"the stub codex never ran in {cwd} (no {RECORD_DIRNAME}/ records)")
    directory = directories[-1]
    process = json.loads((directory / PROCESS_FILE).read_text(encoding="utf-8"))
    return {
        "sequence": int(directory.name),
        "argv": json.loads((directory / ARGV_FILE).read_text(encoding="utf-8")),
        "env": json.loads((directory / ENV_FILE).read_text(encoding="utf-8")),
        "cwd": (directory / CWD_FILE).read_text(encoding="utf-8"),
        "stdin": (directory / STDIN_FILE).read_text(encoding="utf-8"),
        "pid": process["pid"],
        "pgid": process["pgid"],
    }


# --- the program itself -------------------------------------------------------


def main(argv: list[str]) -> int:
    """`argv` is `sys.argv` whole — argv[0] included, as the child received it."""
    cwd = Path.cwd()
    home = Path(os.environ.get("HOME") or cwd)
    control_path = home / CONTROL_FILENAME
    if control_path.exists():
        control = Control(**json.loads(control_path.read_text(encoding="utf-8")))
    else:
        control = Control()

    record_root = cwd / RECORD_DIRNAME
    record_root.mkdir(parents=True, exist_ok=True)
    sequence = 1
    while True:
        directory = record_root / str(sequence)
        try:
            directory.mkdir()
        except FileExistsError:
            sequence += 1
            continue
        break

    def write(name: str, text: str) -> None:
        (directory / name).write_text(text, encoding="utf-8")

    write(ARGV_FILE, json.dumps(list(argv), indent=2))
    write(ENV_FILE, json.dumps(dict(os.environ), indent=2, sort_keys=True))
    write(CWD_FILE, str(cwd))
    write(PROCESS_FILE, json.dumps({"pid": os.getpid(), "pgid": os.getpgid(0)}, indent=2))
    # Last, and only once stdin is drained: a test polling for "the stub is up"
    # waits on the file that proves the prompt arrived.
    write(STDIN_FILE, sys.stdin.read() if not sys.stdin.isatty() else "")

    def on_term(signum: int, _frame: Any) -> None:
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, on_term)

    print(BANNER, flush=True)
    if control.interleave_stderr and control.stdout and control.stderr:
        lines = control.stdout.splitlines(keepends=True)
        print(lines[0], flush=True)
        sys.stderr.write(control.stderr)
        sys.stderr.flush()
        print("".join(lines[1:]), flush=True)
    else:
        if control.stdout:
            print(control.stdout, flush=True)
        if control.stderr:
            sys.stderr.write(control.stderr)
            sys.stderr.flush()

    # A turn happened: write the rollout file under the CODEX_HOME the
    # adapter seeded (measured: CODEX_HOME wins over $HOME/.codex) — the
    # tree the adapter's turn probe reads.
    codex_home_env = os.environ.get(CODEX_HOME_ENV)
    if control.write_rollout and codex_home_env:
        session_id = flag_value(argv, "--session-id") or ""
        path = rollout_path(Path(codex_home_env), session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if control.rollout_text is not None:
            path.write_text(control.rollout_text, encoding="utf-8")
        else:
            path.write_text(
                json.dumps({"type": "session_meta", "session_id": session_id}) + "\n",
                encoding="utf-8",
            )

    if control.sleep_s:
        time.sleep(control.sleep_s)

    return control.exit_code


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    sys.exit(main(sys.argv))
