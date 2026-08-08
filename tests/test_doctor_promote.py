"""The `promote` verb and landed-state loop closure.

Written before the `promote` subcommand exists (T016 precedes T019): until the
implementation lands, tests here fail at runtime. Tests drive `main(argv)`
directly, the same way the existing CLI suites do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.doctor.cli import main
from factory.doctor.models import Status
from factory.doctor.store import connect, get_finding, list_findings


SEED_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "015-factory-doctor"
    / "seed-findings.json"
)


def _db_arg(path: Path) -> list[str]:
    return ["--db", str(path)]


def _report_seed(db_path: Path) -> None:
    assert main(_db_arg(db_path) + ["report", "--batch", str(SEED_FIXTURE)]) == 0


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


@pytest.fixture
def specs_root(tmp_path: Path) -> Path:
    return tmp_path / "specs"


def test_promote_scaffolds_and_marks_findings_promoted(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)

    keys = ["interpreter/fire-and-forget-node-tasks", "temporal/node-child-workflows"]
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "audit-fixups",
            "--keys",
            *keys,
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 0

    spec_dir = specs_root / "audit-fixups"
    assert spec_dir.is_dir()
    assert (spec_dir / "spec.md").is_file()
    assert (spec_dir / "plan.md").is_file()
    assert (spec_dir / "tasks.md").is_file()

    spec_text = (spec_dir / "spec.md").read_text()
    assert spec_text.startswith("---\n")
    assert "state: draft" in spec_text.split("---\n")[1]

    conn = connect(db_path)
    for key in keys:
        f = get_finding(conn, key)
        assert f is not None
        assert f.status is Status.PROMOTED
        assert f.promoted_spec == str(spec_dir)

    # list shows the association
    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0


def test_promote_refuses_existing_directory(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)

    (specs_root / "audit-fixups").mkdir(parents=True)
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "audit-fixups",
            "--keys",
            "interpreter/fire-and-forget-node-tasks",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 1


def test_promote_already_promoted_finding_refuses_naming_spec(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)

    key = "interpreter/fire-and-forget-node-tasks"
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "audit-fixups",
            "--keys",
            key,
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 0

    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "audit-fixups-2",
            "--keys",
            key,
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 1
    conn = connect(db_path)
    assert get_finding(conn, key).promoted_spec == str(specs_root / "audit-fixups")


def test_promote_regressed_finding_allowed(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)
    key = "interpreter/fire-and-forget-node-tasks"

    assert main(_db_arg(db_path) + ["promote", "--slug", "fix1", "--keys", key, "--specs-root", str(specs_root), "--target-repo", str(specs_root.parent)]) == 0
    assert main(_db_arg(db_path) + ["resolve", "--key", key, "--reason", "landed"]) == 0
    # re-report to make it regressed
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-09T10:00:00Z")
    assert main(_db_arg(db_path) + [
        "report",
        "--key",
        key,
        "--category",
        "interpreter",
        "--severity",
        "critical",
        "--summary",
        "it came back",
        "--refs",
        "a:2",
        "--source",
        "probe",
    ]) == 0

    conn = connect(db_path)
    assert get_finding(conn, key).status is Status.REGRESSED

    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "fix2",
            "--keys",
            key,
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 0
    assert get_finding(conn, key).status is Status.PROMOTED
    assert get_finding(conn, key).promoted_spec == str(specs_root / "fix2")


def test_promote_failed_derivation_leaves_nothing_behind(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)

    # Patch scaffold to emit invalid spec text so derivation fails.
    monkeypatch.setattr(
        "factory.doctor.scaffold._build_spec_md",
        lambda *args, **kwargs: "# no work graph\n",
    )

    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "bad-spec",
            "--keys",
            "interpreter/fire-and-forget-node-tasks",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 1
    assert not (specs_root / "bad-spec").exists()

    # retrying the same slug is not blocked
    monkeypatch.undo()
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "bad-spec",
            "--keys",
            "interpreter/fire-and-forget-node-tasks",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 0
    assert (specs_root / "bad-spec").is_dir()


def test_promoted_finding_resolves_when_spec_attested_landed(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)
    key = "interpreter/fire-and-forget-node-tasks"

    assert main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "landed-fix",
            "--keys",
            key,
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    ) == 0

    spec_dir = specs_root / "landed-fix"
    spec_path = spec_dir / "spec.md"
    text = spec_path.read_text()
    # Replace frontmatter state with landed.
    text = text.replace("state: draft", "state: landed")
    spec_path.write_text(text)

    # Any doctor command next runs should resolve the finding.
    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0

    conn = connect(db_path)
    f = get_finding(conn, key)
    assert f.status is Status.RESOLVED
    assert f.resolution == str(spec_dir)
    assert f.resolved_at is not None


def test_promote_requires_at_least_one_key(db_path: Path, specs_root: Path) -> None:
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "empty",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 1


def test_promote_unknown_key_exits_user(
    db_path: Path, specs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    _report_seed(db_path)
    rc = main(
        _db_arg(db_path)
        + [
            "promote",
            "--slug",
            "x",
            "--keys",
            "interpreter/never-heard-of-it",
            "--specs-root",
            str(specs_root),
            "--target-repo",
            str(specs_root.parent),
        ]
    )
    assert rc == 1
