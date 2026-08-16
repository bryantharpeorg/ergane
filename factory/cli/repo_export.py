"""STUB (red run only): the do-nothing export.

Committed on its own so the red transcript answers the question the calibration
asks of every test — what would make this pass if the production code did
nothing? — with a run rather than an opinion.  Replaced wholesale by the
implementation in the next commit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExportResult:
    destination: Path
    stores: tuple[object, ...]
    digest: Path


def open_store(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def export_records(
    *, slug: str, repo: Path, runtime_root: Path, destination: Path
) -> ExportResult:
    destination.mkdir(parents=True, exist_ok=True)
    return ExportResult(destination=destination, stores=(), digest=destination / "digest.md")
