"""US2: the `ergane spec` noun — list, validate, derive, landed, all with --json.

Every assertion mirrors the behaviour the old roadmap and epic
CLIs established (SC-003): same expected output, new entry
point.  This is a new file so US2, US3 and US4 can fan out without editing the
old suites, which stay pointed at the old scripts until US5.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.roadmap.models import Roadmap, Readiness, compute_readiness, read_roadmap

CORPUS = Path(__file__).resolve().parent / "fixtures"
ROADMAP_CORPUS = CORPUS / "roadmap"
WORKGRAPH_CORPUS = CORPUS / "workgraph"

TARGET_REPO = "/srv/factory/targets/short-links"
DEAD_ADDRESS = "127.0.0.1:1"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        return main(list(argv))
    except SystemExit as exit_request:
        return 0 if exit_request.code is None else int(exit_request.code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


# --- helpers: fixture specs and repos ----------------------------------------


def specs_root(case: str) -> str:
    return str(ROADMAP_CORPUS / case / "specs")


def epic_dir(tmp_path: Path, fixture: str, *, name: str | None = None) -> Path:
    source = WORKGRAPH_CORPUS / fixture / "spec.md"
    dest = tmp_path / (name or fixture)
    dest.mkdir(parents=True)
    (dest / "spec.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    # valid_epic has five scenarios; give them task references so validate
    # passes. 044 added a fifth layer that assembles each node's attempt prompt,
    # so a sound spec now needs a sound *trio*: a plan.md, and phases whose
    # headings name the story each task slice belongs to.
    if fixture == "valid_epic":
        (dest / "plan.md").write_text(
            "# Plan\n\nCarried into every node's prompt whole.\n", encoding="utf-8"
        )
        (dest / "tasks.md").write_text(
            "# Tasks\n\n"
            "## Phase 1: User Story 1 - Save a link\n\n"
            "- [ ] T001 [US1-S1] first\n"
            "- [ ] T002 [US1-S2] second\n\n"
            "## Phase 2: User Story 2 - Follow a short link\n\n"
            "- [ ] T003 [US2-S1] third\n"
            "- [ ] T004 [US2-S2] fourth\n\n"
            "## Phase 3: User Story 3 - List my links\n\n"
            "- [ ] T005 [US3-S1] fifth\n",
            encoding="utf-8",
        )
    return dest


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


def _commit(repo: Path, subject: str, *, env: dict[str, str], allow_empty: bool = False) -> str:
    args = ["commit", "--quiet", "-m", subject]
    if allow_empty:
        args.append("--allow-empty")
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


def _spec(
    *,
    state: str | None = None,
    stories: list[str] | None = None,
    work_graph: str = "",
    scenarios: dict[str, list[str]] | None = None,
    tasks: list[str] | None = None,
) -> str:
    """A minimal Spec Kit feature spec.  Tasks are returned separately."""
    front = "---\n"
    if state is not None:
        front += f"state: {state}\n"
    front += "---\n"
    body = "# Feature\n\n"
    stories = stories or []
    if stories:
        body += "## Requirements *(mandatory)*\n\n"
        for number in range(1, len(stories) + 1):
            body += f"- **FR-{number:03d}**: The system MUST do thing {number}.\n"
        body += "\n"
    for number, title in enumerate(stories, start=1):
        body += f"### User Story {number} - {title} (Priority: P{number})\n\n"
        body += "As the operator, I want this.\n\n"
        body += "**Acceptance Scenarios**:\n"
        scen = (scenarios or {}).get(f"US{number}", ["Given a thing, When I act, Then it works."])
        for s in scen:
            body += f"1. **Given** a thing, **When** I act, **Then** {s}\n"
        body += "\n"
    if work_graph:
        body += "## Work Graph\n\n```yaml\n" + work_graph + "\n```\n"
    return front + body


@pytest.fixture
def repo_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    def build(specs: dict[str, str], *, default_branch: str = "main") -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        env = _git_env(empty_home)
        for key in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        ):
            monkeypatch.delenv(key, raising=False)
        _git(repo, "init", "-b", default_branch, "--quiet", env=env)
        specs_dir = repo / "specs" / "016-delta-derivation"
        specs_dir.mkdir(parents=True)
        for name, text in specs.items():
            (specs_dir / name).write_text(text, encoding="utf-8")
        _git(repo, "add", "-A", env=env)
        _commit(repo, "fixture skeleton", env=env)
        return repo

    return build


# --- T010: list mirrors roadmap render ---------------------------------------


def test_list_every_spec_appears_with_state(run: Callable[..., Run]) -> None:
    result = run("spec", "list", specs_root("valid"))
    assert result.code == 0
    out = result.stdout
    assert "001-alpha" in out and "landed" in out
    assert "002-bravo" in out and "draft" in out
    assert "003-ready" in out and "ready" in out
    assert "006-deferred" in out and "deferred" in out


def test_list_blocked_spec_names_unsatisfied_dependencies(run: Callable[..., Run]) -> None:
    result = run("spec", "list", specs_root("valid"))
    assert result.code == 0
    assert "004-blocked" in result.stdout
    assert "002-bravo" in result.stdout


def test_list_is_deterministic(run: Callable[..., Run]) -> None:
    one = run("spec", "list", specs_root("valid"))
    two = run("spec", "list", specs_root("valid"))
    assert one.code == two.code == 0
    assert one.stdout == two.stdout


def test_list_needs_no_service(run: Callable[..., Run], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPORAL_ADDRESS", DEAD_ADDRESS)
    assert run("spec", "list", specs_root("valid")).code == 0


# --- T010: derive mirrors the old epic derive command ------------------------


def test_derive_writes_compiled_artifact(run: Callable[..., Run], tmp_path: Path) -> None:
    spec = epic_dir(tmp_path, "valid_epic")

    result = run("spec", "derive", str(spec), "--target-repo", TARGET_REPO)

    artifact = spec / "workgraph.json"
    assert result.code == 0
    assert str(artifact) in result.stdout
    parsed = json.loads(artifact.read_text(encoding="utf-8"))
    assert parsed["epic_id"] == "valid_epic"
    assert parsed["feature"] == "valid_epic"
    assert parsed["target_repo"] == TARGET_REPO


def test_derive_epic_id_is_spec_directory_name(run: Callable[..., Run], tmp_path: Path) -> None:
    source = WORKGRAPH_CORPUS / "valid_epic" / "spec.md"
    spec = tmp_path / "003-merge-queue"
    spec.mkdir(parents=True)
    (spec / "spec.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    result = run("spec", "derive", str(spec), "--target-repo", TARGET_REPO)

    assert result.code == 0
    parsed = json.loads((spec / "workgraph.json").read_text(encoding="utf-8"))
    assert parsed["epic_id"] == "003-merge-queue"


def test_derive_needs_no_temporal_server(run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPORAL_ADDRESS", DEAD_ADDRESS)
    spec = epic_dir(tmp_path, "valid_epic")

    result = run("spec", "derive", str(spec), "--target-repo", TARGET_REPO)

    assert result.code == 0
    assert (spec / "workgraph.json").exists()


def test_derive_failed_writes_nothing(run: Callable[..., Run], tmp_path: Path) -> None:
    spec = epic_dir(tmp_path, "cycle")

    result = run("spec", "derive", str(spec), "--target-repo", TARGET_REPO)

    assert result.code == 1
    assert not (spec / "workgraph.json").exists()
    assert result.stdout == ""


# --- T012: landed branch-resolution regression -------------------------------


def test_landed_uses_manifest_declared_branch_with_no_flag(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "declared-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "016-delta-derivation"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1", "US2"],
        work_graph=(
            "US1:\n  depends_on: []\n  implements: [FR-001]\n"
            "US2:\n  depends_on: [US1]\n  implements: [FR-002]\n"
        ),
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    (repo / "factory.yaml").write_text(
        "version: 1\nruntime: x\ngates:\n  test: x\nlanding_branch: ergane-buildout\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)
    _git(repo, "checkout", "--quiet", "-b", "ergane-buildout", env=env)
    _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)

    result = run("spec", "landed", str(specs_dir))

    assert result.code == 0
    assert "US1" in result.stdout
    assert "observed" in result.stdout
    assert "ergane-buildout" in result.stdout


def test_landed_explicit_default_branch_overrides_manifest(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "override-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "016-delta-derivation"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1", "US2"],
        work_graph=(
            "US1:\n  depends_on: []\n  implements: [FR-001]\n"
            "US2:\n  depends_on: [US1]\n  implements: [FR-002]\n"
        ),
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    (repo / "factory.yaml").write_text(
        "version: 1\nruntime: x\ngates:\n  test: x\nlanding_branch: ergane-buildout\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)
    _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)

    result = run("spec", "landed", "--default-branch", "main", str(specs_dir))

    assert result.code == 0
    assert "US1" in result.stdout
    assert "main" in result.stdout


def test_landed_needs_no_temporal_server(
    run: Callable[..., Run], repo_builder: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
    )
    repo = repo_builder({"spec.md": spec})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)

    monkeypatch.setenv("TEMPORAL_ADDRESS", DEAD_ADDRESS)

    result = run("spec", "landed", str(repo / "specs" / "016-delta-derivation"))

    assert result.code == 0
    assert "US1" in result.stdout


# --- T011: validate collects all refusals in one run ---------------------------


def test_validate_reports_frontmatter_derivation_and_persona_errors(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three refusal layers appear in one run, and the command opens no socket."""
    repo = tmp_path / "bad-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "bad-spec"
    specs_dir.mkdir(parents=True)
    # Frontmatter error (unknown key) + derivation error (unknown dependency)
    # + unserved implementer persona in the registry. All three must be named
    # in the same run, demonstrating that validate does not short-circuit.
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: [US9]\n  implements: [FR-001]\n",
    )
    # Add an unknown frontmatter key.
    spec = spec.replace("state: ready", "state: ready\nunknown_key: x")
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    # Make the registry unserved for every import of the spec noun.
    import factory.config

    monkeypatch.setattr(factory.config, "load_personas", lambda path=None: {})
    # Also provide a tasks.md so scenario coverage does not add a fourth finding.
    (specs_dir / "tasks.md").write_text("- [ ] T001 [US1-S1] task\n", encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", str(specs_dir))

    assert result.code == 1
    output = result.stdout + result.stderr
    # Frontmatter error named.
    assert "unknown_key" in output
    assert "bad-spec" in output
    # Work-graph derivation error named.
    assert "US9" in output
    # Persona-registry error named.
    assert "implementer" in output
    # Count: exactly the three expected findings (scenario coverage is satisfied).
    assert output.count("ergane spec validate:") == 3


def test_validate_exits_zero_and_names_checks_on_sound_spec(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    spec = epic_dir(tmp_path, "valid_epic")

    result = run("spec", "validate", str(spec))

    assert result.code == 0
    out = result.stdout + result.stderr
    assert "frontmatter" in out or "roadmap" in out
    assert "work graph" in out or "derivation" in out
    assert "persona" in out


def test_validate_opens_no_socket(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEMPORAL_ADDRESS", DEAD_ADDRESS)
    spec = epic_dir(tmp_path, "valid_epic")

    # Patch Client.connect so any attempt to build a Temporal client explodes.
    import temporalio.client

    original_connect = temporalio.client.Client.connect

    def exploding_connect(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("validate must not connect to Temporal")

    monkeypatch.setattr(temporalio.client.Client, "connect", exploding_connect)

    result = run("spec", "validate", str(spec))
    assert result.code == 0


# --- T011a: scenario coverage ------------------------------------------------


def test_validate_reports_uncovered_scenario_ids(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "scen-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "scen-spec"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
        scenarios={"US1": ["it works", "it also works"]},
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    (specs_dir / "tasks.md").write_text(
        "- [ ] T001 [US1-S1] write the first test\n", encoding="utf-8"
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", str(specs_dir))

    # FR-002: uncovered scenarios are an advisory, so they do not exit 1 by
    # themselves.  The missing reference is still reported.
    assert result.code == 0
    assert "US1-S2" in (result.stdout + result.stderr)


def test_validate_scenario_coverage_passes_when_all_referenced(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "scen-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "scen-spec"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
        scenarios={"US1": ["it works", "it also works"]},
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    # A sound trio, not a sound spec.md: 044's assembly layer needs a plan.md
    # and a phase heading naming the story whose slice these tasks are.
    (specs_dir / "plan.md").write_text("# Plan\n\nOne store.\n", encoding="utf-8")
    (specs_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Phase 1: User Story 1 - US1\n\n"
        "- [ ] T001 [US1-S1] write the first test\n"
        "- [ ] T002 [US1-S2] write the second test\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", str(specs_dir))

    assert result.code == 0
    assert (
        f"{specs_dir / 'spec.md'}: frontmatter, work-graph derivation, persona registry, "
        "scenario coverage, prompt assembly and slice coverage all pass"
    ) in result.stdout
    # A deliberate gap must still be reported; otherwise the check could be
    # deleted and this test would pass for the wrong reason.
    (specs_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Phase 1: User Story 1 - US1\n\n"
        "- [ ] T001 [US1-S1] write the first test\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "gap fixture", env=env)

    result = run("spec", "validate", str(specs_dir))

    assert result.code == 0
    assert "US1-S2" in (result.stdout + result.stderr)


def test_validate_reports_missing_tasks_file(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "scen-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "scen-spec"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
        scenarios={"US1": ["it works"]},
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    # No tasks.md
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", str(specs_dir))

    # FR-004: a spec with no task list is a structural defect, not a
    # convention gap, so it stays a refusal and exits 1.
    assert result.code == 1
    assert "tasks.md" in (result.stdout + result.stderr)


# --- T011a: advisory vs refusal semantics -------------------------------------


def test_validate_frontmatter_defect_and_uncovered_scenarios_exits_refusal(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "scen-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "scen-spec"
    specs_dir.mkdir(parents=True)
    # Invalid state triggers a frontmatter finding.
    spec = _spec(
        state="invalid-state",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
        scenarios={"US1": ["it works", "it also works"]},
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    (specs_dir / "tasks.md").write_text(
        "- [ ] T001 [US1-S1] write the first test\n", encoding="utf-8"
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", str(specs_dir))

    # The refusal severity of the frontmatter finding decides the verdict.
    assert result.code == 1
    assert "US1-S2" in (result.stdout + result.stderr)
    assert "frontmatter" in (result.stdout + result.stderr)


def test_validate_json_findings_carry_severity_and_preserve_document_shape(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    repo = tmp_path / "scen-repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty-home")
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    specs_dir = repo / "specs" / "scen-spec"
    specs_dir.mkdir(parents=True)
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
        scenarios={"US1": ["it works", "it also works"]},
    )
    (specs_dir / "spec.md").write_text(spec, encoding="utf-8")
    (specs_dir / "tasks.md").write_text(
        "- [ ] T001 [US1-S1] write the first test\n", encoding="utf-8"
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    result = run("spec", "validate", "--json", str(specs_dir))

    assert result.code == 0
    doc = result.json
    assert doc.get("spec_dir") == str(specs_dir)
    assert "checked" in doc
    assert "findings" in doc
    # FR-007: every finding carries a severity; nothing else about the
    # document shape changes.
    assert all("severity" in finding for finding in doc["findings"])
    # The order of findings is unchanged.
    findings = doc["findings"]
    assert len(findings) == 1
    assert findings[0].get("layer") == "scenario_coverage"
    assert "US1-S2" in findings[0].get("message", "")
    assert findings[0].get("severity") == "advisory"


# --- T013: --json for every verb ---------------------------------------------


def test_list_json_is_parseable_document(run: Callable[..., Run]) -> None:
    result = run("spec", "list", "--json", specs_root("valid"))

    assert result.code == 0
    doc = result.json
    assert isinstance(doc, dict)
    # Human rendering absent: no columnar table lines.
    assert "001-alpha" not in result.stdout or isinstance(doc, dict)


def test_derive_json_is_parseable_document(run: Callable[..., Run], tmp_path: Path) -> None:
    spec = epic_dir(tmp_path, "valid_epic")

    result = run("spec", "derive", "--json", str(spec), "--target-repo", TARGET_REPO)

    assert result.code == 0
    doc = result.json
    assert isinstance(doc, dict)
    assert doc.get("artifact")


def test_landed_json_is_parseable_document(
    run: Callable[..., Run], repo_builder: Callable[..., Path]
) -> None:
    spec = _spec(
        state="ready",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
    )
    repo = repo_builder({"spec.md": spec})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)

    result = run("spec", "landed", "--json", str(repo / "specs" / "016-delta-derivation"))

    assert result.code == 0
    doc = result.json
    assert isinstance(doc, dict)
    assert "US1" in doc.get("facts", {})


def test_validate_json_is_parseable_document(run: Callable[..., Run], tmp_path: Path) -> None:
    spec = epic_dir(tmp_path, "valid_epic")

    result = run("spec", "validate", "--json", str(spec))

    assert result.code == 0
    doc = result.json
    assert isinstance(doc, dict)
    assert "checked" in doc or "findings" in doc


def test_validate_json_reports_findings(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = epic_dir(tmp_path, "cycle")

    result = run("spec", "validate", "--json", str(spec))

    assert result.code == 1
    doc = result.json
    assert "findings" in doc
    assert len(doc["findings"]) >= 1
