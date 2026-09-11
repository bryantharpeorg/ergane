"""US1: a v2 manifest declares the artifacts its gates write."""

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
    FactoryConfigError,
    parse_factory_config,
)
from factory.verify.models import ArtifactDeclaration, ArtifactType, FactoryConfig


BASE_MANIFEST = """
    version: 2
    runtime: bwrap
    gates:
      test: "uv run pytest -q"
      lint: "uv run ruff check ."
"""


def manifest(artifacts: str) -> str:
    return textwrap.dedent(BASE_MANIFEST) + textwrap.dedent(artifacts)


DECLARED_MANIFEST = manifest(
    """
    artifacts:
      - gate: test
        path: ./coverage.xml
        type: coverage
      - gate: lint
        path: reports/../sbom.json
        type: sbom
      - gate: test
        path: reports/scan.json
        type: scan
      - gate: lint
        path: audit.json
        type: opaque
    """
)


def test_declared_artifacts_parse_in_declaration_order() -> None:
    config = parse_factory_config(DECLARED_MANIFEST)

    assert config.artifacts == (
        ArtifactDeclaration(
            gate="test", path="coverage.xml", type=ArtifactType.COVERAGE
        ),
        ArtifactDeclaration(gate="lint", path="sbom.json", type=ArtifactType.SBOM),
        ArtifactDeclaration(gate="test", path="reports/scan.json", type=ArtifactType.SCAN),
        ArtifactDeclaration(gate="lint", path="audit.json", type=ArtifactType.OPAQUE),
    )


@pytest.mark.parametrize(
    ("problem", "tokens"),
    [
        (
            "- {gate: test, path: coverage.xml, type: virus_scan}",
            ("virus_scan", "'sbom'", "'coverage'", "'scan'", "'opaque'"),
        ),
        (
            "- {gate: build, path: coverage.xml, type: coverage}",
            ("build", "'test'", "'lint'"),
        ),
        (
            "- {gate: test, path: /tmp/coverage.xml, type: coverage}",
            ("/tmp/coverage.xml",),
        ),
        (
            "- {gate: test, path: ../coverage.xml, type: coverage}",
            ("../coverage.xml",),
        ),
    ],
)
def test_refuses_invalid_entries_and_names_them(problem: str, tokens: tuple[str, ...]) -> None:
    text = manifest("artifacts:\n      " + problem + "\n")

    with pytest.raises(FactoryConfigError) as error:
        parse_factory_config(text)

    message = str(error.value)
    assert error.value.rule == "artifacts"
    for token in tokens:
        assert token in message, message


def test_no_artifact_declaration_preserves_existing_config_fields() -> None:
    text = manifest("")
    config = parse_factory_config(text)

    legacy = FactoryConfig(
        version=2, runtime="bwrap", gates={"test": "uv run pytest -q", "lint": "uv run ruff check ."}
    )
    for field in dataclasses.fields(FactoryConfig):
        if field.name != "artifacts":
            assert getattr(config, field.name) == getattr(legacy, field.name)
    assert config.artifacts == ()


def test_v1_refuses_artifacts_as_unknown_top_level_key() -> None:
    text = manifest(
        "artifacts:\n      - {gate: test, path: coverage.xml, type: coverage}\n"
    ).replace(
        "version: 2", "version: 1"
    )

    with pytest.raises(FactoryConfigError) as error:
        parse_factory_config(text)

    assert error.value.rule == "unknown_key"
    assert "'artifacts'" in str(error.value)


def test_parser_cli_emits_artifacts_as_json_strings(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_text(DECLARED_MANIFEST, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "factory.verify.factory_yaml", str(path)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("\n") == 1
    parsed = json.loads(result.stdout)
    assert parsed["artifacts"] == [
        {"gate": "test", "path": "coverage.xml", "type": "coverage"},
        {"gate": "lint", "path": "sbom.json", "type": "sbom"},
        {"gate": "test", "path": "reports/scan.json", "type": "scan"},
        {"gate": "lint", "path": "audit.json", "type": "opaque"},
    ]
