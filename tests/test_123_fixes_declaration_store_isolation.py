"""US2 of 123: the fixes-declaration tests build their own findings store.

122/US3 fixed this class in two files and was scoped from a measurement that did
not look at a third. `tests/test_spec_declares_its_fixes.py` resolves a findings
store the way the findings verbs do, and that resolution has two candidates, not
one: `ERGANE_ROOT` names the first, and when no ledger exists there
`_resolve_store_path` falls back to the legacy runtime root *relative to the
working directory* — which, on an operator's host, is the operator's real
ledger. The suite-wide redirect in `tests/conftest.py` pins only the first
candidate, so the second leaked and one test decided its verdict from whatever
findings the machine happened to hold:

    assert 'fixes' in []

Green on a fresh clone, red on the machine that does the building. This module
is the guard. It runs that file as a subprocess under three shapes of host — a
populated operator ledger, no ledger at all, and a ledger that is not a database
— and requires the same green result from each. A test that reads the
operator's store cannot survive all three.

The store the guarded file *does* read is asserted to be its own, from both
ends: this module proves no run touches the runtime-root candidate, and the
guarded test itself asserts the store path validate reports is under its
`tmp_path` (US2-S3).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import factory.doctor.cli as _doctor_cli
from factory.cli.main import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: The module under guard, exactly as the story names it.
_TARGET_FILE = "tests/test_spec_declares_its_fixes.py"

#: The runtime-root directory names an operator's host actually carries. A test
#: in the guarded file that names one of these has pinned itself to the
#: operator's machine (FR-004).
_RUNTIME_ROOT_NAMES = (".factory", ".ergane")

#: Every test in the guarded file must run under every host shape: unlike the
#: two files 122 guarded, none of them is slow enough to buy anything by being
#: deselected, and a filter is a place for coverage to leak out unnoticed.
_EXPECTED_TESTS = 13


def _seed_operator_ledger(db_path: Path) -> None:
    """Write a populated ledger holding a key no fixture in the guarded file declares."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        report(
            conn,
            Finding(
                key="operator/ledger-row",
                category="operator",
                severity=Severity.INFO,
                status=Status.OPEN,
                summary="a row only the operator's host would hold",
                refs=["factory/foo.py:1"],
                notes=None,
                source="test",
                occurrences=1,
                first_seen="2026-08-30T00:00:00Z",
                last_seen="2026-08-30T00:00:00Z",
                promoted_spec=None,
                resolved_at=None,
                resolution=None,
            ),
            seen_at="2026-08-30T00:00:00Z",
        )
    finally:
        conn.close()


def _run_guarded_file(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the guarded file as its own pytest session, rooted at `cwd`.

    A subprocess is the only honest way to vary the host: the legacy candidate
    is a *relative* path, so what it resolves to is decided by the working
    directory of the process that runs the tests.
    """
    env = dict(os.environ)
    # The parent session's own redirect must not travel; the child's copy of
    # `tests/conftest.py` sets its own, which is the condition under test.
    for name in ("ERGANE_ROOT", "FACTORY_ROOT"):
        env.pop(name, None)
    env["PYTHONPATH"] = str(_REPO_ROOT)

    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        str(_REPO_ROOT / _TARGET_FILE),
    ]

    return subprocess.run(
        argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=600
    )


def _assert_green(result: subprocess.CompletedProcess[str], shape: str) -> None:
    transcript = (result.stdout + result.stderr).strip().splitlines()
    tail = "\n".join(transcript[-25:])
    assert result.returncode == 0, (
        f"the fixes-declaration tests are not green on a host whose findings "
        f"store is {shape}:\n{tail}"
    )
    assert f"{_EXPECTED_TESTS} passed" in result.stdout, (
        f"the guarded file no longer runs {_EXPECTED_TESTS} tests, so this run "
        f"proved less than it reports:\n{tail}"
    )


# --- T006 (US2-S1): green on a host that has a real, populated ledger ---------


def test_fixes_declaration_tests_pass_with_a_populated_operator_ledger(
    tmp_path: Path,
) -> None:
    """The direction that is red today: a machine with a findings store.

    The operator's host holds one, and the guarded test read it — passing or
    failing according to which keys that ledger happened to carry rather than
    according to the code under test.
    """
    host = tmp_path / "host"
    _seed_operator_ledger(host / ".factory" / "doctor.db")

    _assert_green(_run_guarded_file(host), "populated")


# --- T007 (US2-S2): green on a host that has no findings store at all ---------


def test_fixes_declaration_tests_pass_with_no_findings_store_anywhere(
    tmp_path: Path,
) -> None:
    """The other direction. Passing only here is exactly the defect (trap 4).

    Seeding the operator's real store to make his host green would deepen the
    dependency rather than remove it, and this test is what says so: the same
    verdict is owed on a machine that has no ledger at all.
    """
    host = tmp_path / "host"
    host.mkdir()

    for name in _RUNTIME_ROOT_NAMES:
        assert not (host / name).exists()
    _assert_green(_run_guarded_file(host), "absent")


# --- T008 (US2-S3, FR-004): the store is the test's own, never the operator's -


def test_fixes_declaration_tests_never_open_the_operator_runtime_root_store(
    tmp_path: Path,
) -> None:
    """A ledger that is not a database: opening it is fatal, ignoring it is free.

    The behavioural half of FR-004. Every store the guarded file resolves must
    be one it built under its own `tmp_path`, so poisoning the store it must
    never resolve has to change nothing — and leave the poison untouched.
    """
    host = tmp_path / "host"
    poisoned = host / ".factory" / "doctor.db"
    poisoned.parent.mkdir(parents=True)
    poisoned.write_bytes(b"this is not a SQLite database\n" * 64)

    _assert_green(_run_guarded_file(host), "poisoned")
    assert poisoned.read_bytes().startswith(b"this is not a SQLite database")


def test_the_guarded_file_names_no_runtime_root(tmp_path: Path) -> None:
    """The static half: no string literal in the guarded file names a runtime root.

    Docstrings are exempt — the argument for an isolation rule may name the
    directory the rule keeps tests out of. Anything the code actually evaluates
    may not, because a literal runtime root is how a store path stops being the
    test's own.
    """
    path = _REPO_ROOT / _TARGET_FILE
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }

    offences: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        hit = next(
            (root for root in _RUNTIME_ROOT_NAMES if root in node.value.lower()), None
        )
        if hit is not None:
            offences.append(f"{_TARGET_FILE}:{node.lineno} names {hit!r}")

    assert offences == [], (
        "the guarded file names the operator's runtime root instead of building "
        "its own store under tmp_path: " + "; ".join(offences)
    )


# --- T009 (US2-S4, FR-005): the absent-store path still says `not checked` ----

_CONTROL_BODY = """
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


def test_validate_reports_the_fixes_layer_not_checked_for_an_absent_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control, end to end through `ergane spec validate` (trap 5).

    089/US3 landed the absent-store skip deliberately: a freshly initialised
    target repo has no store by construction, and refusing there would make
    `fixes:` undeclarable. This story must not change it in either direction —
    not to a refusal, and not to a store validate creates for itself — and the
    check has to sit where an author meets it, which is the command rather than
    the function.
    """
    specs_root = tmp_path / "specs"
    spec_dir = specs_root / "001-control"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        f"---\nstate: draft\nfixes:\n  - any/key\n---\n"
        f"\n# Feature Specification: 001-control\n{_CONTROL_BODY}",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n\nOne reader, one key.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Phase 1: User Story 1 - The thing happens\n\n"
        "- [ ] T001 [US1-S1] prove the thing happens\n",
        encoding="utf-8",
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("ERGANE_ROOT", str(runtime_root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    # Both candidates under tmp_path, so neither can be the operator's.
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-root")

    code = main(["spec", "validate", "--json", str(spec_dir)])
    report_json: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert code == 0, "an absent store must not be a refusal"
    assert report_json["findings"] == []
    assert "fixes" not in report_json["checked"]
    skipped = {entry["layer"]: entry["reason"] for entry in report_json["skipped"]}
    assert "fixes" in skipped
    assert "no findings store at" in skipped["fixes"]
    assert str(runtime_root / "doctor.db") in skipped["fixes"]
    assert not (runtime_root / "doctor.db").exists(), "validate created the store"
