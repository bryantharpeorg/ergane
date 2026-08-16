"""What the engine learned about one repository, in formats that outlive it.

034 US5, FR-013.  `ergane repo forget --export <dir>` writes one JSONL file per
store and one markdown digest, and that is the whole surface.  Four decisions
carry it.

**The repo's rows are the rows in the repo's own stores.**  No store here has a
repo column: `findings` is keyed by finding key, `usage_records` by epic, node
and attempt, `escalations` by a token — and a workflow id is `epic-{epic_id}`
with no repo in it (034 plan, trap 6).  What *is* repo-scoped is the file, since
FR-012 puts each repo's runtime state under its own runtime root.  So selection
is by store location, derived from the registry entry the slug names and never
from the environment: an `ERGANE_ROOT` pointing at the host's own root would
otherwise export the operator's rows under a departing repo's name.

**Read-only, and nothing is created.**  Every store is opened through the same
`mode=ro` door `factory/verify/store.py` opens for reporting callers, where a
write is refused by the driver rather than by this module's care and no file,
directory or schema can be brought into being.  A repo that never ran an epic has
no stores; its export says so with empty files rather than with three new
databases in a repository the engine has just let go of.

**Deterministic by construction.**  Every query names its `ORDER BY`, every
record is built in the store's own column order, and nothing written here comes
from a clock: there is no "exported at" line, because two exports of an untouched
engine must be byte-identical and a timestamp is the one thing that cannot be.
The digest is rendered from the same records the JSONL is, so the two cannot
disagree.

**No secret value leaves.**  Every string passes through one redactor at one
choke point, on the way out of the database and before either writer sees it.
`history_summary` is why: it is a verbatim failure history, and a run whose
output echoed a proxy key put that key in a store.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from factory.verify.store import connect_readonly

#: What replaces a credential-shaped value on its way into an exported file.
REDACTION = "[REDACTED]"

#: Credential shapes redacted on the way out.  Deliberately wider than any one
#: store's contents: the cost of a false positive is an operator seeing
#: `[REDACTED]` where a hash used to be, and the cost of a miss is a key in a
#: file they hand to someone else.
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
)

#: One entry per store: the exported name, the database file under the runtime
#: root, the table, and the column its rows are ordered by.  A tuple rather than
#: a mapping because this order is the digest's order and the byte-identity claim
#: rests on it being written down rather than inherited from a dict.
_STORES = (
    ("findings", "doctor.db", "findings", "key"),
    ("usage", "ledger.db", "usage_records", "key_alias"),
    ("escalations", "verification.db", "escalations", "escalation_id"),
)

#: A finding's recurrence trail, nested into its record so one file still means
#: one store.  Ordered by the autoincrement id: oldest observation first.
_EVENTS_SQL = (
    "SELECT seen_at, source, severity, kind FROM finding_events "
    "WHERE finding_key = ? ORDER BY id"
)


@dataclass(frozen=True)
class StoreExport:
    """One store's contribution: where it was read, and what came out."""

    name: str
    source: Path | None
    rows: int
    file: Path


@dataclass(frozen=True)
class ExportResult:
    """Everything one export wrote, for the caller to report honestly."""

    destination: Path
    stores: tuple[StoreExport, ...]
    digest: Path


def open_store(path: str | Path) -> sqlite3.Connection:
    """Open a store for reading and only for reading.

    `factory.verify.store.connect_readonly` is not verification-specific — it is
    the `mode=ro` URI and nothing else — so all three stores go through it rather
    than through a fourth copy of one line.
    """
    return connect_readonly(path)


def export_records(
    *, slug: str, repo: Path, runtime_root: Path, destination: Path
) -> ExportResult:
    """Write this repo's engine-side records into `destination` (FR-013).

    The caller has already refused a destination inside `runtime_root`; this
    creates the directory and writes exactly four files into it, committing
    nothing and touching no store.
    """
    destination.mkdir(parents=True, exist_ok=True)

    stores: list[StoreExport] = []
    records: dict[str, list[dict[str, Any]]] = {}
    for name, file_name, table, order_by in _STORES:
        source = _locate(file_name, runtime_root=runtime_root, repo=repo)
        rows = _read(source, table=table, order_by=order_by, name=name)
        records[name] = rows
        written = destination / f"{name}.jsonl"
        _write_jsonl(written, rows)
        stores.append(
            StoreExport(name=name, source=source, rows=len(rows), file=written)
        )

    digest = destination / "digest.md"
    digest.write_text(
        _digest(slug=slug, repo=repo, stores=tuple(stores), records=records),
        encoding="utf-8",
    )
    return ExportResult(
        destination=destination, stores=tuple(stores), digest=digest
    )


# --- reading -----------------------------------------------------------------


def _locate(file_name: str, *, runtime_root: Path, repo: Path) -> Path | None:
    """The store's file for this repo, following the data across the rename.

    The same rule `factory/doctor/cli.py::_resolve_store_path` already applies:
    if the resolved root has no such store while the legacy directory does, the
    data is what to follow.  A repo that has never been migrated keeps its
    records under `.factory/`, and an export that only looked at the modern name
    would hand the operator three empty files and call it their history.
    """
    for candidate in (runtime_root / file_name, repo / ".factory" / file_name):
        if candidate.is_file():
            return candidate
    return None


def _read(
    source: Path | None, *, table: str, order_by: str, name: str
) -> list[dict[str, Any]]:
    """Every row of `table`, cleaned, in `order_by` order — or nothing."""
    if source is None:
        return []

    conn = open_store(source)
    try:
        rows = _records(conn, f"SELECT * FROM {table} ORDER BY {order_by}")
        if name == "findings":
            for row in rows:
                row["events"] = _records(conn, _EVENTS_SQL, (row["key"],))
        return rows
    except sqlite3.DatabaseError:
        # A store written by a future ergane, or a file that is not one at all.
        # An export is a courtesy at the end of a departure; it does not get to
        # fail the departure, and an empty file is the honest reading of a store
        # this engine cannot parse.
        return []
    finally:
        conn.close()


def _records(
    conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()
) -> list[dict[str, Any]]:
    """Rows as dicts in the store's own column order, every string cleaned."""
    cursor = conn.execute(sql, tuple(params))
    columns = [column[0] for column in cursor.description]
    out: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        record: dict[str, Any] = {}
        for index, column in enumerate(columns):
            record[column] = _clean(row[index])
        out.append(record)
    return out


def _clean(value: Any) -> Any:
    """The one choke point every exported string passes through."""
    if not isinstance(value, str):
        return value
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(REDACTION, value)
    return value


# --- writing -----------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """One JSON object per line, newline-terminated, UTF-8, no trailing blank."""
    text = ""
    for record in records:
        text += json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")


def _shown(source: Path | None, repo: Path) -> str:
    """Where a store was read from, relative to the repo when it lies inside it."""
    if source is None:
        return "(no store on disk)"
    try:
        return str(source.relative_to(repo))
    except ValueError:
        return str(source)


def _digest(
    *,
    slug: str,
    repo: Path,
    stores: tuple[StoreExport, ...],
    records: dict[str, list[dict[str, Any]]],
) -> str:
    """The human-readable half: what is here, where it came from, how to read it.

    Rendered from the records the JSONL files were written from — not from a
    second read — so the two cannot disagree, and so the redaction that cleaned
    those records covers this file too without a second redactor.
    """
    out = f"# Ergane export — {slug}\n\n"
    out += (
        f"The engine's own record of the repository at `{repo}`, written by "
        "`ergane repo forget --export`. Ergane never reads these files back: "
        "they are yours. Every string here passed through the credential "
        "redactor on the way out, so a value that looked like a key reads as "
        f"`{REDACTION}`.\n\n"
    )

    out += "| store | rows | read from |\n| --- | --- | --- |\n"
    for store in stores:
        out += f"| {store.name} | {store.rows} | {_shown(store.source, repo)} |\n"

    out += "\n## findings.jsonl\n\n"
    out += (
        "One JSON object per line, one line per row of the `findings` table, "
        "ordered by `key`. Each carries an `events` array — its `finding_events` "
        "trail, oldest first — so the recurrence count that decides what gets "
        "promoted travels with the finding rather than behind it.\n\n"
    )
    findings = records["findings"]
    if not findings:
        out += "No findings were ever reported against this repository.\n"
    for finding in findings:
        out += (
            f"- `{finding['key']}` — {finding['severity']}, {finding['status']}, "
            f"{finding['occurrences']} occurrence(s): {finding['summary']}\n"
        )

    out += "\n## usage.jsonl\n\n"
    out += (
        "One JSON object per line, one line per row of `usage_records`, ordered "
        "by `key_alias` — one row per attempt teardown. A null token or spend "
        "column means the proxy never reported it, never that it was zero.\n"
    )

    out += "\n## escalations.jsonl\n\n"
    out += (
        "One JSON object per line, one line per row of `escalations`, ordered by "
        "`escalation_id`, each with the failure history the escalation was "
        "raised over and how it was settled.\n"
    )
    return out
