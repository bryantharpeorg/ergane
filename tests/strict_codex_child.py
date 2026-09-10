#!/usr/bin/env python3
"""A strict disposable child standing in for installed Codex (164-US1).

`tests/stub_codex.py` stands in for the CLI when a test scripts the launch;
its defaults *manufacture* the turn — it writes a rollout whenever CODEX_HOME
is set, so a fake turn can hide the refusal real Codex produces at the
worktree boundary. This one is the strict child the 164 regression suite
drives through the real `CodexAdapter.run_attempt` policy instead:

1. It refuses a missing or non-existent `CODEX_HOME` — the incident's own
   refusal, word for word (2026-09-08, installed Codex: `CODEX_HOME points
   to "…", but that path does not exist`) — rather than manufacturing the
   directory.
2. It refuses a missing configuration rather than manufacturing one: a
   gateway child requires the seeded `config.toml`, a subscription child the
   copied `auth.json`; a home holding neither is refused by name.
3. Only after a successful read does it write its synthetic rollout under
   `$CODEX_HOME/sessions/`, named after an id it generated itself (trap 4) —
   the tree the adapter's turn probe and archive step read.

It records what the child actually received — cwd, HOME, CODEX_HOME, the
configuration bytes it read, whether creating the rollout needed a new
directory — into `.strict-codex/<n>/` under the working directory, because
what a launch boundary delivers is only observable from inside the child.

This child is simulated inference, not proof of a model response: no model,
gateway service, or installed Codex is involved anywhere in this suite.

The refusal exits 1 with the message on stderr, the measured inverse of
Claude Code (155 trap 3), so the archived combined log carries it the way
the classifier reads it.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

#: This file, as the adapter's `codex` binary.
STRICT_CHILD_PATH = Path(__file__).resolve()

#: One directory per launch beneath the worktree, numbered from 1. Distinct
#: from `.stub-codex/` so the two stand-ins never collide in one worktree.
RECORD_DIRNAME = ".strict-codex"

RECORD_FILE = "record.json"

#: Always printed, so `stdout.log` has an assertable line even when the child
#: refuses before writing its record.
BANNER = "strict-codex: launched"

#: The env var naming the per-node CODEX_HOME. The CLI reads it directly
#: (measured 2026-09-08: sessions land under it, not `$HOME/.codex`).
CODEX_HOME_ENV = "CODEX_HOME"

#: The subscription credential the CLI's own default provider reads; the
#: generated gateway configuration the adapter seeds for a gateway attempt.
AUTH_JSON_NAME = "auth.json"
CONFIG_NAME = "config.toml"

#: The incident's measured refusal, word for word, with the path quoted the
#: way installed Codex quotes it.
MISSING_HOME = 'CODEX_HOME points to "{}", but that path does not exist'


def install_as(bin_dir: Path | str, name: str = "codex") -> Path:
    """Symlink this child into `bin_dir` as `codex`, for tests that shim PATH."""
    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / name
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(STRICT_CHILD_PATH)
    return link


def last_record(cwd: Path | str) -> dict[str, Any]:
    """The most recent launch's record; raises if the strict child never ran."""
    root = Path(cwd) / RECORD_DIRNAME
    directories = (
        sorted(root.iterdir(), key=lambda item: int(item.name)) if root.is_dir() else []
    )
    if not directories:
        raise LookupError(
            f"the strict codex child never ran in {cwd} (no {RECORD_DIRNAME}/ records)"
        )
    return json.loads((directories[-1] / RECORD_FILE).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    """`argv` is `sys.argv` whole — argv[0] included, as the child received it."""
    cwd = Path.cwd()
    codex_home_value = os.environ.get(CODEX_HOME_ENV)

    # Strict from the first line: a missing CODEX_HOME, or one whose directory
    # does not exist, is the launch refusing — never a directory this child
    # repairs on the implementation's behalf.
    if not codex_home_value:
        print("CODEX_HOME is not set", file=sys.stderr, flush=True)
        return 1
    codex_home = Path(codex_home_value)
    if not codex_home.is_dir():
        print(MISSING_HOME.format(codex_home_value), file=sys.stderr, flush=True)
        return 1

    # The seeded configuration is read, not manufactured: a gateway child
    # needs the generated `config.toml`; a subscription child needs the
    # copied `auth.json`. A home holding neither is a refusal, not a launch.
    config_path = codex_home / CONFIG_NAME
    auth_path = codex_home / AUTH_JSON_NAME
    if config_path.is_file():
        route = CONFIG_NAME
        config_bytes = config_path.read_bytes()
    elif auth_path.is_file():
        route = AUTH_JSON_NAME
        config_bytes = auth_path.read_bytes()
    else:
        print(
            f'no config.toml or auth.json under CODEX_HOME "{codex_home_value}"',
            file=sys.stderr,
            flush=True,
        )
        return 1

    # A synthetic turn, written only after the reads succeeded — the same
    # ordering installed Codex obeys: the rollout follows the reads.
    sessions = codex_home / "sessions" / "2026" / "09" / "10"
    sessions_existed = sessions.is_dir()
    rollout = sessions / (
        f"rollout-2026-09-10T00-00-00-{os.getpid()}-{uuid.uuid4().hex}.jsonl"
    )
    sessions.mkdir(parents=True, exist_ok=True)
    if route == CONFIG_NAME:
        payload = json.dumps({"type": "session_meta", "read": CONFIG_NAME}) + "\n"
    else:
        payload = json.dumps({"type": "session_meta", "read": AUTH_JSON_NAME}) + "\n"
    rollout.write_text(payload, encoding="utf-8")

    # Read the prompt off stdin only now, so the record proves the pipe was
    # fed; then record what this child actually received.
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ""
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

    record = {
        "cwd": str(cwd),
        "home": os.environ.get("HOME"),
        "codex_home": codex_home_value,
        "codex_home_is_absolute": os.path.isabs(codex_home_value),
        "sessions_dir_preexisted": sessions_existed,
        "read": route,
        "config": config_bytes.decode("utf-8", errors="replace"),
        "rollout": str(rollout),
        "stdin": stdin_text,
    }
    (directory / RECORD_FILE).write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(BANNER, flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    sys.exit(main(sys.argv))