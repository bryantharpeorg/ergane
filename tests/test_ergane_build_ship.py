"""US4: `ergane build ship` collapses validate, derive and dispatch into one pause.

Every test that would touch dispatch stubs `start_command` at the module
attribute, so no Temporal connection is opened.  Ship's fixture is a hand-written
spec directory, never a `ergane spec new` scaffold, so this test stays green when
US3's sentinel gate lands.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

import factory
import factory.cli.nouns.build as build_module
import factory.cli.nouns.spec as spec_module
import factory.config
from factory.cli.errors import EXIT_USER, run_cli
from factory.cli.main import _build_parser, main as ergane_main
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.workgraph.cli import ARTIFACT_NAME
from factory.workgraph.derive import derive_workgraph

ABS_TARGET_REPO = str(Path(__file__).resolve().parent / "fixtures")
MODEL_ALIAS = "test-model"
NO_MODEL_MARKER = "<registry default>"
PERSONAS = {
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model=MODEL_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=5400,
    )
}


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _personas_file(tmp_path: Path, personas: dict[str, Persona]) -> Path:
    """Write a fixture persona registry and return its path."""
    path = tmp_path / "personas.yaml"
    lines = ["# fixture registry"]
    for name, persona in personas.items():
        lines.extend(
            [
                f"{name}:",
                f"  agent: {persona.agent}",
                f"  model: {json.dumps(persona.model)}",
                f"  fallback: {json.dumps(persona.fallback)}",
                f"  skills: {json.dumps(list(persona.skills))}",
                f"  write_scope: {persona.write_scope.value}",
                f"  needs_worktree: {json.dumps(persona.needs_worktree)}",
                f"  timeout: {json.dumps(persona.timeout_s)}",
            ]
        )
        if persona.context_window is not None:
            lines.append(f"  context_window: {persona.context_window}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_ship_command(
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
    spec_dir: Path,
    target_repo: Path,
    start_stub: Callable[[argparse.Namespace], int] | None = None,
    personas: dict[str, Persona] | None = None,
) -> Run:
    """Parse real `build ship` argv and call the reloaded module's `ship_command`.

    `main._build_parser` reloads the noun modules, so `start_command` must be
    patched on the freshly loaded module.  Persona control is through a temporary
    registry file and ``ERGANE_PERSONAS_PATH``; that env variable is read by the
    reloaded ``load_personas`` even though the function object is re-imported.
    """
    if personas is not None:
        registry_path = _personas_file(spec_dir.parent, personas)
        monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(registry_path))
        monkeypatch.delenv("FACTORY_PERSONAS_PATH", raising=False)

    parser = _build_parser()
    args = parser.parse_args(
        ["build", "ship", str(spec_dir), "--target-repo", str(target_repo), *extra]
    )

    # Apply dispatch patch to the freshly loaded module now that parsing is done.
    fresh_build = sys.modules["factory.cli.nouns.build"]
    if start_stub is not None:
        monkeypatch.setattr(fresh_build, "start_command", start_stub)

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        code = run_cli(lambda: fresh_build.ship_command(args))
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return Run(int(code), stdout_capture.getvalue(), stderr_capture.getvalue())


#: A minimal sound spec with three stories, no contention and no sentinels.
SPEC_TEXT = """---
state: ready
---
# Feature: Ship Demo

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First (Priority: P1)

As the operator, I want the first story.

**Acceptance Scenarios**:
1. **Given** a thing, **When** I act, **Then** it works.

### User Story 2 - Second (Priority: P1)

As the operator, I want the second story.

**Acceptance Scenarios**:
1. **Given** a thing, **When** I act, **Then** it works.

### User Story 3 - Third (Priority: P2)

As the operator, I want the third story.

**Acceptance Scenarios**:
1. **Given** a thing, **When** I act, **Then** it works.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: []
US2:
  depends_on: [US1]
  implements: []
US3:
  depends_on: []
  implements: []
```
"""

PLAN_TEXT = "# Plan\n\nOne plan.\n"
TASKS_TEXT = """# Tasks

## Phase 1: User Story 1 - First

- [ ] T001 [US1-S1] implement first story

## Phase 2: User Story 2 - Second

- [ ] T002 [US2-S1] implement second story

## Phase 3: User Story 3 - Third

- [ ] T003 [US3-S1] implement third story
"""


def _make_spec_dir(tmp_path: Path, *, name: str = "ship-demo") -> Path:
    spec_dir = tmp_path / name
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC_TEXT, encoding="utf-8")
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")
    return spec_dir


def _git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Ergane Ship",
        "GIT_AUTHOR_EMAIL": "ship@ergane.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_NAME": "Ergane Ship",
        "GIT_COMMITTER_EMAIL": "ship@ergane.invalid",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed.stdout


def _target_repo(tmp_path: Path) -> Path:
    """A real git repository ship can point --target-repo at."""
    repo = tmp_path / "target-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    (repo / "factory.yaml").write_text(
        "version: 1\nruntime: x\ngates:\n  test: x\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-m", "initial", "--quiet", env=env)
    return repo


def _ship_argv(
    spec_dir: Path,
    target_repo: Path,
    *extra: str,
    specs_root: Path | None = None,
) -> tuple[str, ...]:
    argv = [
        "build",
        "ship",
        str(spec_dir),
        "--target-repo",
        str(target_repo),
    ]
    if specs_root is not None:
        argv += ["--specs-root", str(specs_root)]
    argv += list(extra)
    return tuple(argv)


# --- T029: full stream order and summary with model aliases -----------------


def test_ship_streams_validate_derive_summary_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage output streams in order; summary has persona/model for every node."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)

    result = _run_ship_command(
        monkeypatch,
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: 0,
        personas=dict(PERSONAS),
    )

    assert result.code == 0, result.stderr
    combined = result.stdout + result.stderr

    validate_banner = f"ship: validating {spec_dir / ARTIFACT_NAME}"
    derive_banner = f"ship: deriving {spec_dir / ARTIFACT_NAME}"
    summary_header = re.search(
        r"ship: compiled graph .* \d+ node", combined, re.MULTILINE
    )
    assert summary_header is not None, combined

    validate_pos = combined.find(validate_banner)
    derive_pos = combined.find(derive_banner)
    summary_pos = combined.find("ship: compiled graph")
    assert -1 < validate_pos < derive_pos < summary_pos, (
        f"stream order wrong: validate={validate_pos} derive={derive_pos} "
        f"summary={summary_pos}"
    )

    # Dispatch order is declaration order: us1, us2, us3 (us2 waits for us1 merge).
    dispatch_order = re.search(
        r"dispatch order: (.*)", result.stdout, re.MULTILINE
    )
    assert dispatch_order is not None
    assert dispatch_order.group(1).split() == ["us1", "us2", "us3"]

    node_count = re.search(r"ship: compiled graph .* has (\d+) node", result.stdout, re.MULTILINE)
    assert node_count is not None
    assert node_count.group(1) == "3"

    per_node = re.findall(
        r"^  us[123]  persona implementer  model .*$", result.stdout, re.MULTILINE
    )
    assert len(per_node) == 3, per_node
    for line in per_node:
        assert not line.endswith("model "), (
            f"summary line ends in bare 'model ': {line}"
        )
        assert f"  model {MODEL_ALIAS}" in line


# --- T030: model alias resolution ---------------------------------------------


def test_ship_summary_prints_registry_default_when_persona_has_no_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persona whose model is None resolves to the stated literal."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)

    none_persona = Persona(
        name="implementer",
        agent="none",
        model=None,
        fallback=None,
        skills=(),
        write_scope=WriteScope.READ,
        needs_worktree=True,
        timeout_s=None,
    )

    result = _run_ship_command(
        monkeypatch,
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: 0,
        personas={"implementer": none_persona},
    )

    assert result.code == 0, result.stderr
    per_node = re.findall(
        r"^  us[123]  persona implementer  model .*$", result.stdout, re.MULTILINE
    )
    assert len(per_node) == 3
    for line in per_node:
        assert f"  model {NO_MODEL_MARKER}" in line


def test_ship_refuses_at_validate_when_persona_missing_from_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing persona stops at stage one; summary is never reached."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)
    calls: list[argparse.Namespace] = []

    result = _run_ship_command(
        monkeypatch,
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
        personas={},
    )

    assert result.code != 0
    assert "persona" in result.stderr.lower()
    assert not calls
    assert "ship: compiled graph" not in result.stdout


# --- T031: the confirmation pause ---------------------------------------------


def test_ship_declined_confirmation_returns_exit_user_and_never_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No --yes, declined input: exit 1, cancelled message, no dispatch."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)
    calls: list[Any] = []
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    result = _run_ship_command(
        monkeypatch,
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
        personas=dict(PERSONAS),
    )

    assert result.code == EXIT_USER
    assert "cancelled" in result.stderr.lower()
    assert not calls


def test_ship_eof_reads_as_decline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EOFError at the confirmation is treated as a decline."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)
    calls: list[Any] = []

    def raise_eof(_prompt: str) -> str:
        raise EOFError()

    monkeypatch.setattr("builtins.input", raise_eof)

    result = _run_ship_command(
        monkeypatch,
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
        personas=dict(PERSONAS),
    )

    assert result.code == EXIT_USER
    assert "cancelled" in result.stderr.lower()
    assert not calls


def test_ship_yes_skips_confirmation_and_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--yes passes the confirmation and sets args.graph for dispatch."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)
    calls: list[Any] = []

    result = _run_ship_command(
        monkeypatch,
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
        personas=dict(PERSONAS),
    )

    assert result.code == 0, result.stderr
    assert len(calls) == 1
    graph_path = Path(calls[0].graph)
    assert graph_path.is_file()


# --- T032: stage failures stop ship ------------------------------------------


def test_ship_stops_at_validate_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validation refusal returns validate's code and never derives/dispatches."""
    spec_dir = tmp_path / "bad-spec"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("---\nstate: invalid\n---\n# Bad\n", encoding="utf-8")
    (spec_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    target_repo = _target_repo(tmp_path)
    calls: list[Any] = []

    result = _run_ship_command(
        monkeypatch,
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
    )

    assert result.code != 0
    assert "frontmatter" in result.stderr.lower() or "state" in result.stderr.lower()
    assert not calls
    assert "ship: compiled graph" not in result.stdout


def test_ship_stops_at_derive_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derive failure returns derive's code and never dispatches."""
    spec_dir = _make_spec_dir(tmp_path, name="cycle-spec")
    # Hand-edit the graph into a cycle after validation has already passed.
    text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    text = text.replace(
        "US2:\n  depends_on: [US1]\n  implements: []\nUS3:\n  depends_on: []\n  implements: []",
        "US2:\n  depends_on: [US3]\n  implements: []\nUS3:\n  depends_on: [US2]\n  implements: []",
    )
    (spec_dir / "spec.md").write_text(text, encoding="utf-8")
    target_repo = _target_repo(tmp_path)
    calls: list[Any] = []

    result = _run_ship_command(
        monkeypatch,
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
    )

    assert result.code != 0
    assert "cycle" in result.stderr.lower() or "us2" in result.stderr.lower()
    assert not calls


# --- T033: empty delta --------------------------------------------------------


def test_ship_empty_delta_refuses_naming_expected_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--delta with nothing to build prints 'nothing to build' and refuses clearly."""
    target_repo = _target_repo(tmp_path)
    # Place the spec inside the target repo so derive --delta resolves the repo.
    spec_dir = target_repo / "specs" / "ship-demo"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC_TEXT, encoding="utf-8")
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")

    env = _git_env(tmp_path / "home")
    _git(target_repo, "add", "-A", env=env)
    _git(target_repo, "commit", "-m", "add spec", "--quiet", env=env)

    # Land every story so the delta baseline is satisfied.
    for node_id, story_key, pr in (("us1", "US1", "1"), ("us2", "US2", "2"), ("us3", "US3", "3")):
        _git(
            target_repo,
            "commit",
            "--allow-empty",
            "-m",
            f"{spec_dir.name}/{node_id}: {story_key} (#{pr})",
            env=env,
        )

    result = _run_ship_command(
        monkeypatch,
        "--delta",
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: 0,
    )

    assert result.code != 0
    assert "nothing to build" in result.stdout.lower() or "nothing to build" in result.stderr.lower()
    assert str(spec_dir / ARTIFACT_NAME) in (result.stdout + result.stderr)
    assert "ship: compiled graph" not in result.stdout


# --- T034: parsed namespace completeness --------------------------------------


def test_ship_namespace_has_required_attributes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse produces a namespace with every attribute start/derive read directly."""
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)

    captured: argparse.Namespace | None = None

    def capturing_start(args: argparse.Namespace) -> int:
        nonlocal captured
        captured = args
        return 0

    monkeypatch.setattr(build_module, "start_command", capturing_start)
    monkeypatch.setattr(
        factory.config,
        "load_personas",
        lambda path=None: dict(PERSONAS),
    )

    parser = _build_parser()
    args = parser.parse_args(
        ["build", "ship", str(spec_dir), "--target-repo", str(target_repo), "--yes"]
    )
    code = build_module.ship_command(args)

    assert code == 0
    assert captured is not None
    assert captured.promotion_persona is None
    assert captured.max_concurrent_nodes == 1
    assert captured.output is None
    assert captured.delta is False
    assert captured.graph == str(spec_dir / ARTIFACT_NAME)


# --- T035: --target-repo required ---------------------------------------------


def test_ship_target_repo_required_no_default(
    run: Callable[..., Run],
    tmp_path: Path,
) -> None:
    """Omitting --target-repo is an argparse refusal, not a stage-two path error."""
    spec_dir = _make_spec_dir(tmp_path)

    result = run("build", "ship", str(spec_dir))

    assert result.code == 2
    assert "--target-repo" in result.stderr
    assert "/srv/factory/targets/short-links" not in result.stderr


# --- T036: constituent verbs untouched ---------------------------------------


def test_ship_does_not_move_private_derive_symbol(
    tmp_path: Path,
) -> None:
    """tests/test_graph_paths_are_absolute.py:132 still imports `_derive_command`."""
    import factory.cli.nouns.spec as spec_mod

    assert hasattr(spec_mod, "_derive_command")
    assert callable(spec_mod._derive_command)
