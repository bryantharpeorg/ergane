"""The SQLite journal for launch identity and lifecycle evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import LaunchRecord, RungSelection

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS launches (
    invocation_id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    spec_revision TEXT NOT NULL,
    spec_fingerprint TEXT NOT NULL,
    epic_id TEXT NOT NULL,
    epic_workflow_id TEXT NOT NULL,
    epic_run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    ladder_ordinal INTEGER NOT NULL,
    launch_ordinal INTEGER NOT NULL,
    phase TEXT NOT NULL,
    form TEXT NOT NULL,
    scoring_job_id TEXT,
    scoring_call_ordinal INTEGER,
    delivery_id TEXT,
    key_alias TEXT NOT NULL,
    usage_id INTEGER,
    actual_rung TEXT NOT NULL,
    ladder TEXT NOT NULL,
    transition_reason TEXT NOT NULL,
    outcome TEXT,
    outcome_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_launches_epic_node ON launches (epic_id, node_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    location = Path(path)
    parent = location.parent
    parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(location)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.executescript(_SCHEMA)
    if connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        connection.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    connection.commit()
    return connection


def _selection_json(value: RungSelection) -> str:
    return json.dumps(
        {
            "persona": value.persona,
            "runner": value.runner,
            "route": value.route,
            "model_aliases": list(value.model_aliases),
            "reason": value.reason,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _selection(value: str) -> RungSelection:
    data = json.loads(value)
    return RungSelection(
        persona=data["persona"],
        runner=data["runner"],
        route=data["route"],
        model_aliases=tuple(data["model_aliases"]),
        reason=data["reason"],
    )


def record_launch(path: str | Path, record: LaunchRecord) -> LaunchRecord:
    """Upsert one invocation, preserving its identity across activity retries."""
    if not record.invocation_id:
        raise ValueError("launch identity is absent")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT usage_id, outcome, outcome_reason, key_alias FROM launches"
            " WHERE invocation_id = ?",
            (record.invocation_id,),
        ).fetchone()
        if previous is not None:
            usage_id = record.usage_id if record.usage_id is not None else previous[0]
            outcome = record.outcome if record.outcome is not None else previous[1]
            outcome_reason = (
                record.outcome_reason if record.outcome_reason is not None else previous[2]
            )
            key_alias = record.key_alias or previous[3]
            record = LaunchRecord(
                **{
                    **{field.name: getattr(record, field.name) for field in record.__dataclass_fields__.values()},
                    "usage_id": usage_id,
                    "outcome": outcome,
                    "outcome_reason": outcome_reason,
                    "key_alias": key_alias,
                }
            )
        values = {
            **{field.name: getattr(record, field.name) for field in record.__dataclass_fields__.values()},
            "actual_rung": _selection_json(record.actual_rung),
            "ladder": json.dumps([_selection_json(item) for item in record.ladder]),
        }
        columns = tuple(values)
        connection.execute(
            f"INSERT INTO launches ({', '.join(columns)}) VALUES "
            f"({', '.join(':' + name for name in columns)}) "
            "ON CONFLICT(invocation_id) DO UPDATE SET "
            + ", ".join(f"{name} = excluded.{name}" for name in columns if name != "invocation_id"),
            values,
        )
        connection.commit()
    return record


def link_usage(path: str | Path, invocation_id: str, usage_id: int | None) -> None:
    """Attach usage to an existing launch without rewriting identity facts."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE launches SET usage_id = ? WHERE invocation_id = ?",
            (usage_id, invocation_id),
        )
        connection.commit()


def set_launch_outcome(
    path: str | Path, invocation_id: str, outcome: str, reason: str | None
) -> None:
    """Record a lifecycle ending without rewriting frozen launch facts."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE launches SET outcome = ?, outcome_reason = ? WHERE invocation_id = ?",
            (outcome, reason, invocation_id),
        )
        connection.commit()


def read_launches(path: str | Path) -> tuple[LaunchRecord, ...]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM launches ORDER BY launch_ordinal, invocation_id"
        ).fetchall()
        columns = [item[0] for item in connection.execute("SELECT * FROM launches LIMIT 0").description]
    records = []
    for values in rows:
        data = dict(zip(columns, values))
        data["actual_rung"] = _selection(data.pop("actual_rung"))
        data["ladder"] = tuple(_selection(item) for item in json.loads(data.pop("ladder")))
        records.append(LaunchRecord(**data))
    return tuple(records)
