"""US2: a citation that names a Python symbol is checked against its AST span.

Every test builds a throwaway spec directory **and** a throwaway target repo so
the anchors under test are stable: real `factory/` line numbers move, and a test
that asserted against them would rot for the reason this spec exists (plan trap 8).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": _FIXTURE_IDENTITY[0],
        "GIT_AUTHOR_EMAIL": _FIXTURE_IDENTITY[1],
        "GIT_AUTHOR_DATE": _FIXTURE_TIMESTAMP,
        "GIT_COMMITTER_NAME": _FIXTURE_IDENTITY[0],
        "GIT_COMMITTER_EMAIL": _FIXTURE_IDENTITY[1],
        "GIT_COMMITTER_DATE": _FIXTURE_TIMESTAMP,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed.stdout


def _commit(repo: Path, subject: str, *, env: dict[str, str]) -> str:
    _git(repo, "commit", "--quiet", "-m", subject, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _make_target_repo(tmp_path: Path, module_text: str) -> Path:
    """A tracked target repo containing `src/widget.py` with the supplied text."""
    home = tmp_path / "empty-home"
    home.mkdir()
    repo = tmp_path / "target-repo"
    repo.mkdir()
    env = _git_env(home)
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    src = repo / "src"
    src.mkdir()
    (src / "widget.py").write_text(module_text, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "initial commit", env=env)
    return repo


def _minimal_spec(state: str) -> str:
    return (
        "---\n"
        f"state: {state}\n"
        "---\n"
        "# Feature\n\n"
        "## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do the thing.\n\n"
        "### User Story 1 - Do the thing (Priority: P1)\n\n"
        "As an operator, I want this.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        "## Work Graph\n\n"
        "```yaml\n"
        "US1:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "```\n"
    )


def _make_spec_dir(
    tmp_path: Path,
    target_repo: Path,
    plan_text: str,
    state: str = "landed",
) -> Path:
    """A spec directory whose only possible anchor findings come from `plan.md`."""
    spec_dir = tmp_path / "001-anchor-symbol"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(_minimal_spec(state), encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Phase 1: User Story 1 - Do the thing\n\n"
        "- [ ] T001 [US1-S1] write the test\n",
        encoding="utf-8",
    )
    return spec_dir


_MODULE_WITH_ONE_FUNCTION = (
    '"""A widget module."""\n\n'
    "def do_thing():\n"
    "    return 1\n"
)


_MODULE_WITH_DOTTED_METHOD = (
    '"""A widget module."""\n\n'
    "class Widget:\n"
    "    def do_thing(self):\n"
    "        return 1\n"
)


_MODULE_WITH_DUPLICATE_NAME = (
    '"""A widget module."""\n\n'
    "def do_thing():\n"
    "    return 1\n\n"
    "class Widget:\n"
    "    def do_thing(self):\n"
    "        return 2\n"
)


# --- T013 [P] [US2] (spec US2-S1) ---------------------------------------------


def test_symbol_anchor_outside_span_is_reported(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A cited line past `end_lineno` names the symbol and its real span."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    # `do_thing` occupies lines 3-4 in widget.py; cite line 5.
    plan = "# Plan\n\nSee `src/widget.py:5` — `do_thing`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0  # landed state keeps anchor findings advisory
    doc = result.json
    assert "symbol_anchors" in doc["checked"]
    findings = [f for f in doc["findings"] if f["layer"] == "symbol_anchors"]
    assert len(findings) == 1
    message = findings[0]["message"]
    assert "do_thing" in message
    assert "5" in message
    assert "3-4" in message or "3–4" in message or "3:4" in message
    assert findings[0]["severity"] == "advisory"


def test_symbol_anchor_outside_span_reports_dotted_name(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A dotted citation resolves on its last segment and reports the real span."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_DOTTED_METHOD)
    # `Widget.do_thing` is at lines 4-5; cite line 6.
    plan = "# Plan\n\nSee `src/widget.py:6` — `Widget.do_thing`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    doc = result.json
    findings = [f for f in doc["findings"] if f["layer"] == "symbol_anchors"]
    assert len(findings) == 1
    assert "do_thing" in findings[0]["message"]
    assert findings[0]["severity"] == "advisory"


def test_symbol_anchor_duplicate_name_is_satisfied_by_any_definition(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A name defined twice is not reported when the cited line hits either span."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_DUPLICATE_NAME)
    # `do_thing` first at lines 3-4, second at lines 6-7; cite the second.
    plan = "# Plan\n\nSee `src/widget.py:7` — `do_thing`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    doc = result.json
    assert "symbol_anchors" in doc["checked"]
    assert not any(f["layer"] == "symbol_anchors" for f in doc["findings"])


# --- T014 [P] [US2] (spec US2-S2) — the control --------------------------------


def test_symbol_anchor_inside_span_reports_nothing(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A cited line inside the symbol span is silent."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    # `do_thing` is at lines 3-4; cite line 3.
    plan = "# Plan\n\nSee `src/widget.py:3` — `do_thing`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    doc = result.json
    assert "symbol_anchors" in doc["checked"]
    assert not any(f["layer"] == "symbol_anchors" for f in doc["findings"])


def test_symbol_anchor_control_can_fail(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Move the same citation one line past `end_lineno` and the control turns red."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    # Inside span.
    plan_inside = "# Plan\n\nSee `src/widget.py:4` — `do_thing`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan_inside)
    good = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))
    assert good.code == 0
    assert not any(f["layer"] == "symbol_anchors" for f in good.json["findings"])

    # One line past end_lineno.
    plan_outside = "# Plan\n\nSee `src/widget.py:5` — `do_thing`.\n"
    (spec_dir / "plan.md").write_text(plan_outside, encoding="utf-8")
    bad = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))
    assert bad.code == 0
    findings = [f for f in bad.json["findings"] if f["layer"] == "symbol_anchors"]
    assert len(findings) == 1
    assert "do_thing" in findings[0]["message"]


# --- T015 [P] [US2] (spec US2-S3) ---------------------------------------------


def test_absent_symbol_is_reported_distinctly(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A named symbol that does not exist gets its own finding kind."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    plan = "# Plan\n\nSee `src/widget.py:3` — `missing_func`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    findings = [f for f in result.json["findings"] if f["layer"] == "symbol_anchors"]
    assert len(findings) == 1
    message = findings[0]["message"]
    assert "missing_func" in message
    # Distinct from the line-outside-span report.
    assert "absent" in message.lower() or "not defined" in message.lower()


# --- T016 [P] [US2] (spec US2-S4) ---------------------------------------------


def test_citation_without_symbol_name_gets_no_symbol_claim(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A bare `path.py:NN` citation is left to US1; US2 invents no symbol."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    plan = "# Plan\n\nSee `src/widget.py:99`.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", "--json", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert "symbol_anchors" in result.json["checked"]
    # US2 must not invent a symbol claim for a citation that names none.
    assert not any(f["layer"] == "symbol_anchors" for f in result.json["findings"])


# --- Layer registration -------------------------------------------------------


def test_symbol_anchors_layer_appears_in_all_pass_sentence(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Trap 12: a layer that ran and found nothing must still be named in the summary."""
    target_repo = _make_target_repo(tmp_path, _MODULE_WITH_ONE_FUNCTION)
    plan = "# Plan\n\nNothing to anchor here.\n"
    spec_dir = _make_spec_dir(tmp_path, target_repo, plan)

    result = run("spec", "validate", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    assert "symbol anchors" in result.stdout
