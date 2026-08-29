"""US3 of 089: `ergane spec validate` checks `fixes:` against the findings ledger.

Every fixture here builds its own specs corpus and findings store under
`tmp_path` (trap 7).  `ERGANE_ROOT` is pointed at the store's parent directory
so `spec validate` resolves the store the same way the findings verbs do without
touching the operator's real runtime root.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import warnings
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str, ergane_root: Path | None = None) -> Run:
        if ergane_root is not None:
            monkeypatch.setenv("ERGANE_ROOT", str(ergane_root))
            monkeypatch.delenv("FACTORY_ROOT", raising=False)
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


#: A minimal Spec Kit body that satisfies the layers validate already runs.
_SOUND_BODY = """
## Requirements *(mandatory)*

- **FR-001**: The system MUST do the thing.

### User Story 1 - The thing happens (Priority: P1)

As the operator, I want the thing.

**Acceptance Scenarios**:

1. **Given** a thing, **When** I act, **Then** it works.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
"""

_TRIO_TASKS = (
    "# Tasks\n\n"
    "## Phase 1: User Story 1 - The thing happens\n\n"
    "- [ ] T001 [US1-S1] prove the thing happens\n"
)


#: Deprecation warnings can leak into stderr from unrelated code paths; suppress
#: them once at module load so tests see only validate's own transcript.
warnings.filterwarnings("ignore", category=DeprecationWarning)


def _sound_spec_dir(specs_root: Path, spec_dir: str, frontmatter: str) -> Path:
    """Write a spec trio whose only variable is the frontmatter block."""
    directory = specs_root / spec_dir
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(
        f"---\n{frontmatter}\n---\n{_SOUND_BODY}", encoding="utf-8"
    )
    (directory / "plan.md").write_text(
        "# Plan\n\nOne reader, one key.\n", encoding="utf-8"
    )
    (directory / "tasks.md").write_text(_TRIO_TASKS, encoding="utf-8")
    return directory


def _seed_store(db_path: Path, keys: list[str]) -> None:
    """Create a findings store holding open rows for the given keys."""
    conn = connect(db_path)
    try:
        for key in keys:
            category, _, slug = key.partition("/")
            report(
                conn,
                Finding(
                    key=key,
                    category=category,
                    severity=Severity.INFO,
                    status=Status.OPEN,
                    summary=f"Summary for {key}",
                    refs=["factory/foo.py:1"],
                    notes=None,
                    source="test",
                    occurrences=1,
                    first_seen="2026-08-29T00:00:00Z",
                    last_seen="2026-08-29T00:00:00Z",
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at="2026-08-29T00:00:00Z",
            )
    finally:
        conn.close()


# --- T015 (US3-S1): an unknown fixes key is refused ----------------------------


def test_validate_refuses_unknown_fixes_key_naming_key_and_store(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A `fixes:` key absent from the ledger is refused, naming the key and path."""
    specs_root = tmp_path / "specs"
    db_path = tmp_path / "doctor.db"
    _seed_store(db_path, ["present/key"])
    spec_dir = _sound_spec_dir(
        specs_root, "001-absent", "state: draft\nfixes:\n  - absent/key\n"
    )

    result = run("spec", "validate", str(spec_dir), ergane_root=tmp_path)

    assert result.code == 1
    output = result.stdout + result.stderr
    assert "absent/key" in output
    assert str(db_path) in output


# --- T016 (US3-S2): only known keys pass and report count ------------------------


def test_validate_passes_when_all_fixes_keys_are_known_and_reports_count(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A `fixes:` list naming only ledger rows passes and reports how many it checked."""
    specs_root = tmp_path / "specs"
    db_path = tmp_path / "doctor.db"
    _seed_store(db_path, ["a/one", "b/two"])
    spec_dir = _sound_spec_dir(
        specs_root, "001-known", "state: draft\nfixes:\n  - a/one\n  - b/two\n"
    )

    result = run("spec", "validate", "--json", str(spec_dir), ergane_root=tmp_path)

    assert result.code == 0
    doc = result.json
    assert "fixes" in doc["checked"]
    assert "fixes" not in [entry["layer"] for entry in doc["skipped"]]
    output = result.stdout + result.stderr
    assert "verified 2 finding key(s)" in output
    assert str(db_path) in output


# --- T017 (US3-S3): an absent store is `not checked`, not a refusal --------------


def test_validate_reports_fixes_not_checked_when_store_is_absent(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A runtime root with no ledger does not prove a key wrong; validate skips."""
    specs_root = tmp_path / "specs"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    store_path = runtime_root / "doctor.db"
    spec_dir = _sound_spec_dir(
        specs_root, "001-no-store", "state: draft\nfixes:\n  - any/key\n"
    )

    result = run("spec", "validate", "--json", str(spec_dir), ergane_root=runtime_root)

    assert result.code == 0
    doc = result.json
    assert "fixes" not in doc["checked"]
    skipped = [entry for entry in doc["skipped"] if entry["layer"] == "fixes"]
    assert len(skipped) == 1
    assert str(store_path) in skipped[0]["reason"]
    assert "refusal" not in result.stderr


# --- T018 (US3-S4): a spec with no `fixes:` key is unchanged ---------------------


def test_validate_unchanged_for_spec_without_fixes(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A spec that omits `fixes:` takes no new code path and gets the old verdict."""
    specs_root = tmp_path / "specs"
    db_path = tmp_path / "doctor.db"
    _seed_store(db_path, ["a/one"])
    # The control: no fixes key, but a store is present so a bug that always runs
    # the fixes layer would have data to compare against.
    spec_dir = _sound_spec_dir(specs_root, "001-no-fixes", "state: draft\n")

    json_result = run("spec", "validate", "--json", str(spec_dir), ergane_root=tmp_path)
    human_result = run("spec", "validate", str(spec_dir), ergane_root=tmp_path)

    assert json_result.code == 0
    doc = json_result.json
    assert "fixes" not in doc["checked"]
    assert "fixes" not in [entry["layer"] for entry in doc["skipped"]]
    assert doc["findings"] == []

    assert human_result.code == 0
    assert (
        f"{spec_dir / 'spec.md'}: frontmatter, work-graph derivation, persona registry, "
        "scenario coverage, prompt assembly and slice coverage all pass"
    ) in human_result.stdout


# --- T019 (FR-006 / trap 6): validate does not create the store it reads ---------


def test_validate_does_not_create_missing_store(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Running validate against a path with no store leaves that path non-existent."""
    specs_root = tmp_path / "specs"
    runtime_root = tmp_path / "empty-runtime"
    runtime_root.mkdir()
    store_path = runtime_root / "doctor.db"
    spec_dir = _sound_spec_dir(
        specs_root, "001-create-guard", "state: draft\nfixes:\n  - any/key\n"
    )

    assert not store_path.exists()
    result = run("spec", "validate", str(spec_dir), ergane_root=runtime_root)
    assert not store_path.exists()

    assert result.code == 0
    assert "not checked" in result.stderr
    assert str(store_path) in result.stderr
