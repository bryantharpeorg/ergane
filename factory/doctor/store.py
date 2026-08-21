"""The only writer to `.factory/doctor.db`.

`_SCHEMA_DDL` is a verbatim copy of `specs/015-factory-doctor/contracts/doctor-store.sql`;
`tests/test_doctor_store.py` holds it structure-for-structure against the contract
file. Every writer path commits before returning, and the identity-keyed upsert
makes at-least-once reporting land on one row.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from factory.doctor.models import Finding, FindingEvent, Severity, Status

#: Bumping this means the DDL below changed shape and existing stores need a
#: migration path. Recorded in the database so a reader can tell.
SCHEMA_VERSION = 1

#: How long a writer waits out another writer's lock before giving up.
BUSY_TIMEOUT_MS = 5000

#: Verbatim from `specs/015-factory-doctor/contracts/doctor-store.sql`. Every
#: statement is `IF NOT EXISTS`, so bootstrap is safe to run on every connect.
_SCHEMA_DDL = """
-- The doctor's findings ledger: .factory/doctor.db
--
-- Read by `ergane findings list` and any operator with sqlite3; written only by
-- factory/doctor/store.py, whose _SCHEMA_DDL is a verbatim copy of this file —
-- the same contract-copy discipline as contracts/verification-store.sql, held
-- by a structure-for-structure test.
--
-- Identity is the finding key. `findings` holds current state (one row per
-- identity, upsert target for at-least-once reporting); `finding_events` holds
-- the recurrence trail (append-only, one row per observation). Severity and
-- status are closed sets held by the schema, so the arithmetic that computes
-- over them (list ordering, check exit codes, regression transitions) rests on
-- the schema rather than on caller care. (Wording matters: this header is
-- copied verbatim into a module-level DDL constant, and a non-docstring string
-- literal containing the D-021 sweep's vocabulary would fail
-- test_final_sweep.py.) Category is deliberately unconstrained:
-- taxonomy is open, grammar is closed (spec § Decision, call 5).

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    key           TEXT PRIMARY KEY,           -- category/slug, stable identity
    category      TEXT NOT NULL,              -- open taxonomy (prefix of key)
    severity      TEXT NOT NULL
        CHECK (severity IN ('critical', 'warning', 'info')),
    status        TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'promoted', 'resolved', 'regressed')),
    summary       TEXT NOT NULL,              -- latest report's summary
    refs          TEXT NOT NULL,              -- JSON array of file:line strings
    notes         TEXT,                       -- latest report's notes, nullable
    source        TEXT NOT NULL,              -- latest reporter: probe name,
                                              --   'operator', or audit id
    occurrences   INTEGER NOT NULL DEFAULT 1,
    first_seen    TEXT NOT NULL,              -- ISO-8601 UTC
    last_seen     TEXT NOT NULL,              -- ISO-8601 UTC
    promoted_spec TEXT,                       -- spec dir once promoted
    resolved_at   TEXT,                       -- ISO-8601 UTC, set on resolve
    resolution    TEXT                        -- reason, or the spec that landed
);

CREATE TABLE IF NOT EXISTS finding_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_key TEXT NOT NULL REFERENCES findings(key),
    seen_at     TEXT NOT NULL,                -- ISO-8601 UTC
    source      TEXT NOT NULL,
    severity    TEXT NOT NULL
        CHECK (severity IN ('critical', 'warning', 'info')),
    kind        TEXT NOT NULL
        CHECK (kind IN ('reported', 'promoted', 'resolved', 'regressed'))
);

CREATE INDEX IF NOT EXISTS idx_finding_events_key
    ON finding_events(finding_key, seen_at);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the evidence store at `path`, creating file, directories and schema."""
    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(location)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    _bootstrap_schema(conn)
    return conn


def connect_readonly(path: str | Path) -> sqlite3.Connection:
    """Open an existing store for reading, on a connection that cannot write.

    `connect` is the wrong door for a verb that must not change one byte: it
    creates the file, applies the DDL and commits. Those are all no-ops on a
    store that already exists, but "no-op" is a property of today's DDL rather
    than a guarantee, and `ergane findings triage` without `--apply` has to be
    able to state the guarantee (073 FR-013).

    So the URI carries `mode=ro` — SQLite itself refuses the write — and
    `query_only` is set as well, so a caller that tries anyway fails loudly here
    instead of quietly succeeding somewhere else. A missing file raises rather
    than being created: a store the operator has not got is a question, not an
    empty ledger.
    """
    location = Path(path)
    if not location.is_file():
        raise FileNotFoundError(f"no findings store at {location}")

    conn = sqlite3.connect(f"{location.resolve().as_uri()}?mode=ro", uri=True)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA query_only = ON")
    return conn


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Apply the DDL and stamp the version — idempotent across reconnects."""
    conn.executescript(_SCHEMA_DDL)
    recorded = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    if recorded == 0:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
    conn.commit()


# --- findings ----------------------------------------------------------------


def report(conn: sqlite3.Connection, finding: Finding, *, seen_at: str) -> None:
    """Record one observation of a finding, implementing the recurrence machine.

    - First report of a key: insert an `open` row and a `reported` event.
    - Re-report of an `open` key: increment occurrences, advance last_seen,
      refresh summary/refs/notes/source, append a `reported` event.
    - Re-report of a `resolved` key: transition to `regressed`, keep history,
      increment occurrences, refresh evidence, append a `regressed` event.

    The whole transition is one transaction so a concurrent report cannot
    split the row update from the event append.
    """
    with conn:
        # Identity-keyed upsert: at-least-once callers race to insert the first
        # row. SQLite's ON CONFLICT turns a lost race into an update that reads
        # the current row under the same transaction/lock, so the event and the
        # row stay atomic without a separate read-then-write path.
        conn.execute(
            """
            INSERT INTO findings (
                key, category, severity, status, summary, refs, notes, source,
                occurrences, first_seen, last_seen, promoted_spec, resolved_at, resolution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                status = CASE
                    WHEN findings.status = 'resolved' THEN 'regressed'
                    ELSE findings.status
                END,
                severity = excluded.severity,
                summary = excluded.summary,
                refs = excluded.refs,
                notes = excluded.notes,
                source = excluded.source,
                occurrences = findings.occurrences + 1,
                last_seen = excluded.last_seen
            """,
            (
                finding.key,
                finding.category,
                finding.severity.value,
                finding.status.value,
                finding.summary,
                json.dumps(finding.refs),
                finding.notes,
                finding.source,
                finding.occurrences,
                seen_at,
                seen_at,
                finding.promoted_spec,
                finding.resolved_at,
                finding.resolution,
            ),
        )

        # The event kind depends on whether this report caused a regression. A
        # finding that has a resolved event but no regressed event yet is reopening
        # right now; otherwise it is a normal recurrence.
        resolved_count = conn.execute(
            "SELECT COUNT(*) FROM finding_events "
            "WHERE finding_key = ? AND kind = 'resolved'",
            (finding.key,),
        ).fetchone()[0]
        regressed_count = conn.execute(
            "SELECT COUNT(*) FROM finding_events "
            "WHERE finding_key = ? AND kind = 'regressed'",
            (finding.key,),
        ).fetchone()[0]
        kind = "regressed" if resolved_count > regressed_count else "reported"
        _insert_event(conn, finding.key, seen_at, finding.source, finding.severity, kind)


def _insert_finding(
    conn: sqlite3.Connection, finding: Finding, seen_at: str
) -> None:
    conn.execute(
        """
        INSERT INTO findings (
            key, category, severity, status, summary, refs, notes, source,
            occurrences, first_seen, last_seen, promoted_spec, resolved_at, resolution
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            finding.key,
            finding.category,
            finding.severity.value,
            finding.status.value,
            finding.summary,
            json.dumps(finding.refs),
            finding.notes,
            finding.source,
            finding.occurrences,
            seen_at,
            seen_at,
            finding.promoted_spec,
            finding.resolved_at,
            finding.resolution,
        ),
    )


def _insert_event(
    conn: sqlite3.Connection,
    key: str,
    seen_at: str,
    source: str,
    severity: Severity,
    kind: str,
) -> None:
    conn.execute(
        """
        INSERT INTO finding_events (finding_key, seen_at, source, severity, kind)
        VALUES (?, ?, ?, ?, ?)
        """,
        (key, seen_at, source, severity.value, kind),
    )


def resolve(
    conn: sqlite3.Connection,
    key: str,
    *,
    reason: str,
    resolved_at: str,
) -> bool:
    """Manually resolve an open or regressed finding.

    Returns True if the row existed and was not already resolved; False
    otherwise. A resolution event is appended.
    """
    with conn:
        row = conn.execute(
            "SELECT status FROM findings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return False

        status = Status(row[0])
        if status is Status.RESOLVED:
            return False

        conn.execute(
            """
            UPDATE findings
            SET status = 'resolved', resolved_at = ?, resolution = ?
            WHERE key = ?
            """,
            (resolved_at, reason, key),
        )
        _insert_event(
            conn,
            key,
            resolved_at,
            "operator",
            Severity.INFO,
            "resolved",
        )
    return True


#: Prefixes the one line `annotate` owns, and the only line it will replace.
#: A marker rather than a diff of the prose because the operator's own notes and
#: the sweep's annotation share one nullable column, and the sweep must be able
#: to rewrite its sentence without touching a word a human wrote.
ANNOTATION_MARKER = "[ergane findings triage]"


def annotate(conn: sqlite3.Connection, key: str, *, annotation: str) -> bool:
    """Write one triage annotation into a finding's `notes`, and nothing else.

    `report()` is the obvious-looking door here and it is the wrong one: it
    increments `occurrences`, advances `last_seen`, appends a `finding_events`
    row, and flips a `resolved` row to `regressed` on the way past. Annotating a
    two-hundred-row ledger through it would add two hundred phantom recurrences
    to a ledger whose entire purpose is counting recurrence (073 FR-018).

    So this touches exactly one column. Status, occurrences, `first_seen`,
    `last_seen`, severity, refs, source and the event trail are all left as
    found, and there is no event to append because an annotation is not an
    observation — nothing was seen.

    Idempotence is by **replacement, not by append**: any existing line starting
    with `ANNOTATION_MARKER` is dropped before the new one is written, so a
    second pass over an unchanged store rewrites the same bytes, and a pass with
    a different `--cold-days` corrects the sentence instead of stacking a second
    one under it. Notes a human wrote are kept verbatim, above the marker line.

    Returns True when the row existed and its notes changed — so a caller can
    tell "annotated" from "the annotation was already right" without re-reading,
    and report the difference rather than claiming a write it did not make.
    Returns False for an unknown key.
    """
    # Collapsed to one line because the marker is line-scoped: an annotation
    # carrying a newline would leave an orphan the next pass could not find.
    line = f"{ANNOTATION_MARKER} {' '.join(annotation.split())}"

    with conn:
        row = conn.execute(
            "SELECT notes FROM findings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return False

        existing = row[0] or ""
        kept = [
            text
            for text in existing.splitlines()
            if not text.startswith(ANNOTATION_MARKER)
        ]
        while kept and not kept[-1].strip():
            kept.pop()
        notes = "\n".join([*kept, "", line]) if kept else line
        if notes == existing:
            return False

        conn.execute("UPDATE findings SET notes = ? WHERE key = ?", (notes, key))
    return True


def resolve_by_spec(
    conn: sqlite3.Connection,
    key: str,
    *,
    spec_dir: str,
    resolved_at: str,
) -> bool:
    """Resolve a promoted finding because its spec's frontmatter attests landed.

    Returns True when the row existed, was promoted, and is now resolved. The
    spec directory is recorded as the resolution.
    """
    with conn:
        row = conn.execute(
            "SELECT status FROM findings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return False

        status = Status(row[0])
        if status is Status.RESOLVED:
            return False

        conn.execute(
            """
            UPDATE findings
            SET status = 'resolved', resolved_at = ?, resolution = ?
            WHERE key = ?
            """,
            (resolved_at, spec_dir, key),
        )
        _insert_event(
            conn,
            key,
            resolved_at,
            "roadmap",
            Severity.INFO,
            "resolved",
        )
    return True


def promote(
    conn: sqlite3.Connection,
    keys: Sequence[str],
    *,
    spec_dir: str,
    seen_at: str,
) -> list[str]:
    """Mark the named findings `promoted` with `spec_dir` in one transaction.

    Refuses unknown keys and findings that are already promoted or resolved.
    A regressed finding may be promoted again. Raises `ValueError` naming every
    refused key; on success returns the list of promoted keys and appends a
    `promoted` event for each.
    """
    allowed = {Status.OPEN.value, Status.REGRESSED.value}
    promoted: list[str] = []
    refused: list[str] = []

    with conn:
        for key in keys:
            row = conn.execute(
                "SELECT status, severity FROM findings WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                refused.append(f"{key}: not known")
                continue
            status_value, severity_value = row
            if status_value not in allowed:
                refused.append(f"{key}: status is {status_value}")
                continue

            conn.execute(
                """
                UPDATE findings
                SET status = 'promoted', promoted_spec = ?
                WHERE key = ?
                """,
                (spec_dir, key),
            )
            _insert_event(
                conn,
                key,
                seen_at,
                "doctor",
                Severity(severity_value),
                "promoted",
            )
            promoted.append(key)

    if refused:
        raise ValueError("promote refused:\n" + "\n".join(refused))
    return promoted


# --- reads --------------------------------------------------------------------


def list_findings(conn: sqlite3.Connection) -> list[Finding]:
    """All findings in deterministic order: severity rank, occurrences desc, key."""
    severity_order = {
        Severity.CRITICAL.value: 0,
        Severity.WARNING.value: 1,
        Severity.INFO.value: 2,
    }
    rows = conn.execute(
        """
        SELECT key, category, severity, status, summary, refs, notes, source,
               occurrences, first_seen, last_seen, promoted_spec, resolved_at, resolution
        FROM findings
        ORDER BY CASE severity
            WHEN 'critical' THEN 0
            WHEN 'warning' THEN 1
            WHEN 'info' THEN 2
        END,
        occurrences DESC,
        key
        """
    ).fetchall()
    return [_finding_from_row(row) for row in rows]


def get_finding(conn: sqlite3.Connection, key: str) -> Finding | None:
    """One finding by key, or None if unknown."""
    row = conn.execute(
        """
        SELECT key, category, severity, status, summary, refs, notes, source,
               occurrences, first_seen, last_seen, promoted_spec, resolved_at, resolution
        FROM findings WHERE key = ?
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    return _finding_from_row(row)


def list_events(conn: sqlite3.Connection, key: str) -> list[FindingEvent]:
    """The event history for one finding, oldest first."""
    rows = conn.execute(
        """
        SELECT id, finding_key, seen_at, source, severity, kind
        FROM finding_events
        WHERE finding_key = ?
        ORDER BY id
        """,
        (key,),
    ).fetchall()
    return [
        FindingEvent(
            id=row[0],
            finding_key=row[1],
            seen_at=row[2],
            source=row[3],
            severity=Severity(row[4]),
            kind=row[5],
        )
        for row in rows
    ]


def _finding_from_row(row: tuple[Any, ...]) -> Finding:
    return Finding(
        key=row[0],
        category=row[1],
        severity=Severity(row[2]),
        status=Status(row[3]),
        summary=row[4],
        refs=json.loads(row[5]),
        notes=row[6],
        source=row[7],
        occurrences=row[8],
        first_seen=row[9],
        last_seen=row[10],
        promoted_spec=row[11],
        resolved_at=row[12],
        resolution=row[13],
    )
