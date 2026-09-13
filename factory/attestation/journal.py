"""The SQLite journal for launch identity and lifecycle evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from factory.attestation.models import AttemptGitEvidence, GitFileChange, JudgeDelivery, JudgeEvaluationRecord, LaunchRecord, RungSelection
from factory.env import resolve_env_path
from factory.attestation.usage import UsageObservation

SCHEMA_VERSION = 1
DEFAULT_JOURNAL_PATH = ".factory/attestation.db"
FACTORY_JOURNAL_PATH_ENV = "FACTORY_ATTESTATION_DB"
ERGANE_JOURNAL_PATH_ENV = "ERGANE_ATTESTATION_DB"

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
CREATE TABLE IF NOT EXISTS usage_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invocation_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL UNIQUE,
    serving_model TEXT,
    model_alias TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    request_count INTEGER,
    spend_usd REAL
);
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(evidence_id)
);
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


def journal_path() -> Path:
    return resolve_env_path(ERGANE_JOURNAL_PATH_ENV, FACTORY_JOURNAL_PATH_ENV, DEFAULT_JOURNAL_PATH)


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
        connection.row_factory = sqlite3.Row
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


def record_usage_observation(path: str | Path, record: UsageObservation) -> UsageObservation:
    """Persist one source row by its immutable source identity."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        values = {
            **{field.name: getattr(record, field.name) for field in record.__dataclass_fields__.values()}
        }
        columns = tuple(name for name in values if name != "id")
        connection.execute(
            f"INSERT INTO usage_observations ({', '.join(columns)}) VALUES "
            f"({', '.join(':' + name for name in columns)}) "
            "ON CONFLICT(source_id) DO UPDATE SET "
            + ", ".join(f"{name} = excluded.{name}" for name in columns if name != "source_id"),
            values,
        )
        row = connection.execute(
            "SELECT id FROM usage_observations WHERE source_id = ?",
            (record.source_id,),
        ).fetchone()
        connection.commit()
    return UsageObservation(**{**values, "id": row[0]})


def read_usage_observations(path: str | Path) -> tuple[UsageObservation, ...]:
    with connect(path) as connection:
        rows = connection.execute("SELECT * FROM usage_observations ORDER BY id").fetchall()
        columns = [
            item[0]
            for item in connection.execute(
                "SELECT * FROM usage_observations LIMIT 0"
            ).description
        ]
    return tuple(UsageObservation(**dict(zip(columns, row))) for row in rows)


def _record(path: str | Path, record: object, evidence_id: str) -> None:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO evidence_records (evidence_id, payload) VALUES (?, ?)"
            " ON CONFLICT(evidence_id) DO UPDATE SET payload = excluded.payload",
            (evidence_id, json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))),
        )
        connection.commit()


def _decode(payload: str, model: type[JudgeEvaluationRecord | AttemptGitEvidence], nested: str) -> JudgeEvaluationRecord | AttemptGitEvidence:
    data = json.loads(payload)
    data[nested] = tuple((JudgeDelivery if nested == "deliveries" else GitFileChange)(**item) for item in data[nested])
    return model(**data)


def _read(path: str | Path, model: type[JudgeEvaluationRecord | AttemptGitEvidence], nested: str) -> tuple:
    with connect(path) as connection:
        rows = connection.execute("SELECT payload FROM evidence_records ORDER BY evidence_id")
        return tuple(_decode(row[0], model, nested) for row in rows)


def record_scoring_evaluation(
    path: str | Path, record: JudgeEvaluationRecord
) -> JudgeEvaluationRecord:
    _record(path, record, record.evaluation_id)
    return record


def read_scoring_evaluations(path: str | Path) -> tuple[JudgeEvaluationRecord, ...]:
    records = _read(path, JudgeEvaluationRecord, "deliveries")
    return tuple(sorted(records, key=lambda item: (item.scoring_call_ordinal, item.evaluation_id)))


def record_attempt_evidence(
    path: str | Path, record: AttemptGitEvidence
) -> AttemptGitEvidence:
    _record(path, record, record.evidence_id)
    return record


def read_attempt_evidence(path: str | Path) -> tuple[AttemptGitEvidence, ...]:
    return tuple(_read(path, AttemptGitEvidence, "files"))
