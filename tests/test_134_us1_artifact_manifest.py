"""US1 declares gate artifacts in `factory.yaml` and carries them typed."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    PARSE_CLI_REJECTED,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
)
from factory.verify.models import ArtifactDeclaration, ArtifactType, FactoryConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_MODULE = "factory.verify.factory_yaml"


def _yaml(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def _artifact_manifest(
    artifacts: str = """
          - gate: test
            path: coverage.xml
            type: coverage
""",
    *,
    version: int = 2,
) -> str:
    return _yaml(
        f"""
        version: {version}
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        artifacts:
{artifacts}
        """
    )


def test_artifact_declarations_parse_in_declaration_order() -> None:
    config = parse_factory_config(
        _artifact_manifest(
            """
              - gate: test
                path: coverage.xml
                type: coverage
              - gate: test
                path: sbom.json
                type: sbom
              - gate: test
                path: audit.json
                type: scan
              - gate: test
                path: signature.bin
                type: opaque
            """,
        )
    )

    assert config.artifacts == (
        ArtifactDeclaration(gate="test", path="coverage.xml", type=ArtifactType.COVERAGE),
        ArtifactDeclaration(gate="test", path="sbom.json", type=ArtifactType.SBOM),
        ArtifactDeclaration(gate="test", path="audit.json", type=ArtifactType.SCAN),
        ArtifactDeclaration(gate="test", path="signature.bin", type=ArtifactType.OPAQUE),
    )
    assert isinstance(config, FactoryConfig)


@pytest.mark.parametrize(
    ("artifact_type", "expected"),
    [
        ("manifest", r"'manifest'"),
        ("SBOM", r"'SBOM'"),
    ],
)
def test_an_unknown_artifact_type_is_refused(artifact_type: str, expected: str) -> None:
    with pytest.raises(FactoryConfigError) as caught:
        parse_factory_config(
            _artifact_manifest(
                f"""
                  - gate: test
                    path: report.txt
                    type: {artifact_type}
                """,
            )
        )

    assert caught.value.rule == "artifacts"
    assert expected in str(caught.value)
    for permitted_type in ("sbom", "coverage", "scan", "opaque"):
        assert permitted_type in str(caught.value)


def test_an_undeclared_gate_is_refused() -> None:
    with pytest.raises(FactoryConfigError) as caught:
        parse_factory_config(
            _artifact_manifest(
                """
                  - gate: lint
                    path: coverage.xml
                    type: coverage
                """,
            )
        )

    assert caught.value.rule == "artifacts"
    message = str(caught.value)
    assert "'lint'" in message
    assert "'test'" in message


@pytest.mark.parametrize(
    ("path",),
    [
        ("/coverage.xml",),
        ("../coverage.xml",),
        ("reports/../../coverage.xml",),
    ],
)
def test_an_artifact_path_outside_the_repository_is_refused(path: str) -> None:
    with pytest.raises(FactoryConfigError) as caught:
        parse_factory_config(
            _artifact_manifest(
                f"""
                  - gate: test
                    path: {path}
                    type: coverage
                """,
            )
        )

    assert caught.value.rule == "artifacts"
    assert repr(path) in str(caught.value)


def test_a_manifest_without_artifacts_keeps_every_previous_field() -> None:
    manifest = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        timeouts:
          test: 600
        """
    )

    config = parse_factory_config(manifest)
    baseline = FactoryConfig(
        version=2,
        runtime="bwrap",
        gates={"test": "uv run pytest -q"},
        timeouts={"test": 600},
    )

    for field in dataclasses.fields(baseline):
        if field.name == "artifacts":
            continue
        assert getattr(config, field.name) == getattr(baseline, field.name)
    assert config.artifacts == ()


def test_artifacts_are_unknown_on_a_v1_manifest() -> None:
    with pytest.raises(FactoryConfigError) as caught:
        parse_factory_config(
            _artifact_manifest(version=1),
        )

    assert caught.value.rule == "unknown_key"
    assert "'artifacts'" in str(caught.value)
    assert "schema v1" in str(caught.value)


def test_the_parser_cli_renders_artifacts_as_strings(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_text(_artifact_manifest(), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", CLI_MODULE, str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == PARSE_CLI_OK
    document = json.loads(completed.stdout)
    assert document["artifacts"] == [
        {"gate": "test", "path": "coverage.xml", "type": "coverage"},
    ]


@pytest.mark.parametrize(
    ("declared", "normalised"),
    [
        ("./coverage.xml", "coverage.xml"),
        ("reports/../coverage.xml", "coverage.xml"),
    ],
)
def test_artifact_paths_are_carried_in_git_spelling(
    declared: str, normalised: str
) -> None:
    config = parse_factory_config(
        _artifact_manifest(
            f"""
              - gate: test
                path: {declared}
                type: coverage
            """,
        )
    )

    assert config.artifacts[0].path == normalised


@pytest.mark.parametrize(
    ("field_name",),
    [
        ("gate",),
        ("path",),
        ("type",),
    ],
)
def test_a_required_artifact_field_is_refused_by_the_library(
    field_name: str,
) -> None:
    lines = {
        "gate": "          path: coverage.xml\n          type: coverage",
        "path": "          gate: test\n          type: coverage",
        "type": "          gate: test\n          path: coverage.xml",
    }
    with pytest.raises(FactoryConfigError) as caught:
        parse_factory_config(_artifact_manifest(lines[field_name]))

    assert caught.value.rule == "artifacts"
    message = str(caught.value)
    assert field_name in message
    assert "gate" in message or "path" in message or "type" in message


def test_a_required_artifact_field_is_refused_by_the_cli(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        _artifact_manifest(
            """
              - path: coverage.xml
                type: coverage
            """,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "-m", CLI_MODULE, str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == PARSE_CLI_REJECTED
    assert completed.stderr.count("KeyError") == 0
    assert completed.stderr.count("Traceback") == 0
    assert "artifacts" in completed.stderr
    assert "'path'" in completed.stderr
    assert completed.stdout == ""
