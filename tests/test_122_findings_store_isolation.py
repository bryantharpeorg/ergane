"""US3 of 122: the 089 fixes-layer tests build their own findings store.

Those two test modules resolve a findings store the way the findings verbs do.
That resolution has two candidates, not one: `ERGANE_ROOT` names the first, and
when no ledger exists there `_resolve_store_path` falls back to the legacy
runtime root *relative to the working directory* — which, on an operator's host,
is the operator's real ledger. The suite-wide redirect in `tests/conftest.py`
pins only the first candidate, so the second one leaked, and three of the eleven
tests in those two files decided their verdict from whatever findings the
machine happened to hold:

    [fixes] spec declares unknown finding key(s): any/key (store: .factory/doctor.db)

This module is the guard. It runs those two files as a subprocess under three
shapes of host — a populated operator ledger, no ledger at all, and a ledger
that is not a database — and requires the same green result from each. A test
that reads the operator's store cannot survive all three.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import factory.doctor.cli as _doctor_cli
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report
# 133-US5 relocated `_check_fixes` to `factory/spec/layers.py`; the import is
# at module scope, so the new home is named here at module scope too.
from factory.spec.layers import _check_fixes

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: The two modules under guard, exactly as the story names them.
_TARGET_FILES = (
    "tests/test_089_validate_checks_fixes.py",
    "tests/test_089_promote_declares_fixes.py",
)

#: Deselected from the host-shape matrix below, and this is the whole of it.
#: The corpus test spawns `spec validate` once per fixes-less spec in the
#: repository and costs ~18s — a hundred times the other ten tests combined —
#: and no host shape can change its outcome, because `_check_fixes` returns
#: before it resolves a store for a spec that omits `fixes:` and every spec that
#: test validates omits it. It still runs in the ordinary suite. Every run below
#: asserts the filter matched exactly one test, so a rename cannot turn this
#: into a silent skip of something else.
_DESELECTED = "test_validate_fixes_less_specs_in_real_corpus_unchanged"

#: The runtime-root directory names an operator's host actually carries. A test
#: in the guarded files that names one of these has pinned itself to the
#: operator's machine (FR-006).
_RUNTIME_ROOT_NAMES = (".factory", ".ergane")


def _seed_operator_ledger(db_path: Path) -> None:
    """Write a populated ledger holding a key no 089 fixture ever declares."""
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


def _run_guarded_files(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the two 089 files as their own pytest session, rooted at `cwd`.

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
        "-k",
        f"not {_DESELECTED}",
        *(str(_REPO_ROOT / name) for name in _TARGET_FILES),
    ]

    return subprocess.run(
        argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=600
    )


def _assert_green(result: subprocess.CompletedProcess[str], shape: str) -> None:
    transcript = (result.stdout + result.stderr).strip().splitlines()
    tail = "\n".join(transcript[-25:])
    assert result.returncode == 0, (
        f"the 089 fixes-layer tests are not green on a host whose findings "
        f"store is {shape}:\n{tail}"
    )
    assert "1 deselected" in result.stdout, (
        f"the {_DESELECTED!r} filter no longer matches exactly one test, so "
        f"this run skipped something it did not mean to:\n{tail}"
    )


# --- T011 (US3-S1): green on a host that has a real, populated ledger ---------


def test_089_fixes_tests_pass_with_a_populated_operator_ledger(tmp_path: Path) -> None:
    """The direction that is red today: a machine with a findings store."""
    host = tmp_path / "host"
    _seed_operator_ledger(host / ".factory" / "doctor.db")

    _assert_green(_run_guarded_files(host), "populated")


# --- T012 (US3-S2): green on a host that has no findings store at all ---------


def test_089_fixes_tests_pass_with_no_findings_store_anywhere(tmp_path: Path) -> None:
    """The other direction. Passing only here is exactly the defect."""
    host = tmp_path / "host"
    host.mkdir()

    for name in _RUNTIME_ROOT_NAMES:
        assert not (host / name).exists()
    _assert_green(_run_guarded_files(host), "absent")


# --- T013 (US3-S3, FR-006): no test resolves a store under the operator's root -


def test_089_fixes_tests_never_open_the_operator_runtime_root_store(
    tmp_path: Path,
) -> None:
    """A ledger that is not a database: opening it is fatal, ignoring it is free.

    The behavioural half of FR-006. Every store the guarded tests resolve must
    be one they built, so poisoning the store they must never resolve has to
    change nothing.
    """
    host = tmp_path / "host"
    poisoned = host / ".factory" / "doctor.db"
    poisoned.parent.mkdir(parents=True)
    poisoned.write_bytes(b"this is not a SQLite database\n" * 64)

    _assert_green(_run_guarded_files(host), "poisoned")
    assert poisoned.read_bytes().startswith(b"this is not a SQLite database")


def test_no_guarded_test_names_the_operator_runtime_root() -> None:
    """The static half: no string literal in either file names a runtime root.

    Docstrings are exempt — the argument for an isolation rule may name the
    directory the rule keeps tests out of. Anything the code actually evaluates
    may not.
    """
    offences: list[str] = []
    for name in _TARGET_FILES:
        path = _REPO_ROOT / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            hit = next(
                (root for root in _RUNTIME_ROOT_NAMES if root in node.value.lower()),
                None,
            )
            if hit is not None:
                offences.append(f"{name}:{node.lineno} names {hit!r}")

    assert offences == [], (
        "a guarded test names the operator's runtime root instead of building "
        "its own store under tmp_path: " + "; ".join(offences)
    )


# --- T014 (US3-S4, FR-007): the absent-store path still says `not checked` ----


def test_fixes_layer_reports_not_checked_for_an_absent_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. An absent ledger does not prove a key wrong, so it is skipped.

    089/US3 landed this deliberately: a freshly initialised target repo has no
    store by construction, and refusing there would make `fixes:` undeclarable.
    This story must not change it, in either direction — not to a refusal, and
    not to a store validate creates for itself.
    """
    spec_dir = tmp_path / "specs" / "001-control"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        "---\nstate: draft\nfixes:\n  - any/key\n---\n\n# Control\n", encoding="utf-8"
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("ERGANE_ROOT", str(runtime_root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    # Both candidates under tmp_path, so neither can be the operator's.
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-root")

    findings: list[object] = []
    information: list[object] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    _check_fixes(spec_dir, findings, information, skipped, checked)

    assert findings == [], "an absent store must not be a refusal"
    assert "fixes" not in checked
    assert [entry["layer"] for entry in skipped] == ["fixes"]
    assert "no findings store at" in skipped[0]["reason"]
    assert str(runtime_root / "doctor.db") in skipped[0]["reason"]
    assert not (runtime_root / "doctor.db").exists(), "validate created the store"
