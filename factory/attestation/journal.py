"""The SQLite journal for launch identity and lifecycle evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from factory.attestation.models import (
    JudgeDelivery,
    JudgeEvaluationRecord,
    LaunchRecord,
    AttemptGitEvidence,
    GitFileChange,
    RungSelection,
)
from factory.attestation.usage import UsageObservation

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
CREATE TABLE IF NOT EXISTS judge_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    scoring_job_id TEXT NOT NULL,
    scoring_call_ordinal INTEGER NOT NULL,
    invocation_id TEXT NOT NULL,
    key_alias TEXT NOT NULL,
    criteria_fingerprint TEXT NOT NULL,
    tested_revision TEXT NOT NULL,
    status TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    runner TEXT NOT NULL,
    route TEXT NOT NULL,
    backend TEXT NOT NULL,
    scenario_results TEXT NOT NULL,
    feedback TEXT NOT NULL,
    parse_error TEXT,
    deliveries TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    request_count INTEGER,
    spend_usd REAL,
    usage_status TEXT NOT NULL,
    usage_error TEXT,
    truncated_input INTEGER NOT NULL,
    gates_shown INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judge_evaluations_job
    ON judge_evaluations (scoring_job_id, scoring_call_ordinal);
CREATE TABLE IF NOT EXISTS attempt_git_evidence (
    evidence_id TEXT PRIMARY KEY,
    epic_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    dispatch TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    attempted_commit TEXT NOT NULL,
    verified_commit TEXT NOT NULL,
    files TEXT NOT NULL,
    log_tail TEXT NOT NULL,
    log_truncated INTEGER NOT NULL,
    tests_executed TEXT NOT NULL,
    coverage_status TEXT NOT NULL
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


def record_scoring_evaluation(
    path: str | Path, record: JudgeEvaluationRecord
) -> JudgeEvaluationRecord:
    """Persist one scoring result idempotently by its evaluation identity."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        values = {
            **{
                field.name: getattr(record, field.name)
                for field in record.__dataclass_fields__.values()
            },
            "scenario_results": json.dumps(
                [list(result) for result in record.scenario_results],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "deliveries": json.dumps(
                [
                    {
                        "delivery_ordinal": delivery.delivery_ordinal,
                        "status": delivery.status,
                        "error": delivery.error,
                        "response_id": delivery.response_id,
                    }
                    for delivery in record.deliveries
                ],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "truncated_input": int(record.truncated_input),
            "gates_shown": int(record.gates_shown),
        }
        columns = tuple(values)
        connection.execute(
            f"INSERT INTO judge_evaluations ({', '.join(columns)}) VALUES "
            f"({', '.join(':' + name for name in columns)}) "
            "ON CONFLICT(evaluation_id) DO UPDATE SET "
            + ", ".join(
                f"{name} = excluded.{name}" for name in columns if name != "evaluation_id"
            ),
            values,
        )
        connection.commit()
    return record


def read_scoring_evaluations(
    path: str | Path, scoring_job_id: str | None = None
) -> tuple[JudgeEvaluationRecord, ...]:
    """Read persisted evaluations, oldest scoring call first."""
    with connect(path) as connection:
        connection.row_factory = sqlite3.Row
        where = "" if scoring_job_id is None else "WHERE scoring_job_id = ?"
        arguments: tuple[Any, ...] = ()
        if scoring_job_id is not None:
            arguments = (scoring_job_id,)
        rows = connection.execute(
            "SELECT * FROM judge_evaluations "
            f"{where} ORDER BY scoring_call_ordinal, evaluation_id",
            arguments,
        ).fetchall()

    records: list[JudgeEvaluationRecord] = []
    for row in rows:
        results = tuple(
            (item[0], bool(item[1]), item[2])
            for item in json.loads(row["scenario_results"])
        )
        deliveries = tuple(
            JudgeDelivery(
                delivery_ordinal=item["delivery_ordinal"],
                status=item["status"],
                error=item["error"],
                response_id=item["response_id"],
            )
            for item in json.loads(row["deliveries"])
        )
        records.append(
            JudgeEvaluationRecord(
                evaluation_id=row["evaluation_id"],
                scoring_job_id=row["scoring_job_id"],
                scoring_call_ordinal=row["scoring_call_ordinal"],
                invocation_id=row["invocation_id"],
                key_alias=row["key_alias"],
                criteria_fingerprint=row["criteria_fingerprint"],
                tested_revision=row["tested_revision"],
                status=row["status"],
                model_alias=row["model_alias"],
                runner=row["runner"],
                route=row["route"],
                backend=row["backend"],
                scenario_results=results,
                feedback=row["feedback"],
                parse_error=row["parse_error"],
                deliveries=deliveries,
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                cache_read_tokens=row["cache_read_tokens"],
                cache_write_tokens=row["cache_write_tokens"],
                request_count=row["request_count"],
                spend_usd=row["spend_usd"],
                usage_status=row["usage_status"],
                usage_error=row["usage_error"],
                truncated_input=bool(row["truncated_input"]),
                gates_shown=bool(row["gates_shown"]),
            )
        )
    return tuple(records)


def record_attempt_evidence(
    path: str | Path, record: AttemptGitEvidence
) -> AttemptGitEvidence:
    """Persist one exact Git snapshot by its evidence identity."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        values = {
            **{
                field.name: getattr(record, field.name)
                for field in record.__dataclass_fields__.values()
            },
            "files": json.dumps(
                [
                    {
                        "path": item.path,
                        "status": item.status,
                        "old_path": item.old_path,
                        "binary": item.binary,
                    }
                    for item in record.files
                ],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "log_truncated": int(record.log_truncated),
            "tests_executed": json.dumps(list(record.tests_executed), separators=(",", ":")),
        }
        columns = tuple(values)
        connection.execute(
            f"INSERT INTO attempt_git_evidence ({', '.join(columns)}) VALUES "
            f"({', '.join(':' + name for name in columns)}) "
            "ON CONFLICT(evidence_id) DO UPDATE SET "
            + ", ".join(f"{name} = excluded.{name}" for name in columns if name != "evidence_id"),
            values,
        )
        connection.commit()
    return record


def read_attempt_evidence(path: str | Path) -> tuple[AttemptGitEvidence, ...]:
    """Read retained Git evidence, evidence-id ordered for stable reports."""
    with connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM attempt_git_evidence ORDER BY evidence_id"
        ).fetchall()
    records: list[AttemptGitEvidence] = []
    for row in rows:
        files = tuple(
            GitFileChange(
                path=item["path"],
                status=item["status"],
                old_path=item["old_path"],
                binary=item["binary"],
            )
            for item in json.loads(row["files"])
        )
        records.append(
            AttemptGitEvidence(
                evidence_id=row["evidence_id"],
                epic_id=row["epic_id"],
                node_id=row["node_id"],
                attempt=row["attempt"],
                dispatch=row["dispatch"],
                base_commit=row["base_commit"],
                attempted_commit=row["attempted_commit"],
                verified_commit=row["verified_commit"],
                files=files,
                log_tail=row["log_tail"],
                log_truncated=bool(row["log_truncated"]),
                tests_executed=tuple(json.loads(row["tests_executed"])),
                coverage_status=row["coverage_status"],
            )
        )
    return tuple(records)
