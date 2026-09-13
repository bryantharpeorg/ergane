"""Real parser behavior for the attestation packet noun."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from factory.cli.main import main
from tests.test_attestation_archive import SUBJECT, _write, _selector


def _run(*args: str) -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


def _export_args(root: Path, output: Path, *selectors: str, strict: bool = False) -> list[str]:
    args = [
        "attestation", "export", "--root", str(root),
        "--subject", SUBJECT, "--output", str(output),
    ]
    for selector in selectors:
        args.extend(("--selector", selector))
    if strict:
        args.append("--strict")
    return args


def test_cli_selects_export_relocates_and_offline_verifies(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    code, output, _ = _run(
        "attestation", "show", "--root", str(root), "--subject", SUBJECT,
        "--revision", "attempt-2",
    )
    assert code == 0
    document = json.loads(output)
    assert document["subject"] == SUBJECT
    assert document["latest_launch"]["outcome"] == "succeeded"

    archive = root / "cli-packet.zip"
    code, output, _ = _run(*_export_args(root, archive, _selector(2)))
    assert code == 0
    result = json.loads(output)
    assert result["revision"] == result["content_revision"]
    assert result["complete"] is True
    assert output

    relocated = tmp_path / "relocated" / "cli-packet.zip"
    relocated.parent.mkdir()
    shutil.move(archive, relocated)
    shutil.rmtree(root / "source-worktree")
    code, output, _ = _run("attestation", "verify", str(relocated), "--strict")
    assert code == 0
    assert json.loads(output)["subject"] == SUBJECT


def test_cli_refuses_ambiguous_subjects_and_incomplete_strict_export(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    code, _, error = _run("attestation", "show", "--root", str(root), "--subject", SUBJECT)
    assert code == 1
    assert "ambiguous" in error

    archive = root / "strict.zip"
    code, _, error = _run(
        *_export_args(root, archive, _selector(1), _selector(2), _selector(3), strict=True)
    )
    assert code == 1
    assert "incomplete" in error
    assert not archive.exists()


def test_show_and_verify_do_not_change_the_evidence_root(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    archive = root / "readonly.zip"
    code, _, _ = _run(*_export_args(root, archive, _selector(2)))
    assert code == 0

    def state() -> list[tuple[Path, int, int]]:
        return sorted(
            (path, path.stat().st_mode, path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path != archive
        )

    before = state()
    code, _, _ = _run("attestation", "show", "--root", str(root), "--subject", SUBJECT, "--revision", "attempt-2")
    code += _run("attestation", "verify", str(archive))[0]
    assert code == 0
    assert state() == before


def test_missing_evidence_root_is_read_only(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    code, _, error = _run("attestation", "show", "--root", str(root), "--subject", SUBJECT)
    assert code == 1
    assert "missing" in error
    assert not root.exists()
