"""US3: a compiled graph means the same thing in both processes.

`ergane spec derive` resolves `--specs-root` and `--target-repo` to absolute
paths before writing the artifact, so a worker whose cwd differs can still read
the right spec tree.  `ergane build start` refuses a graph that still carries a
relative path, naming the field and value, before any key is minted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from factory.cli.nouns.build import WorkGraphError, load_workgraph
from factory.workgraph.cli import derive_command
from factory.workgraph.models import WorkGraph

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "workgraph" / "valid_epic"


def _existing_target_repo() -> str:
    """A real absolute path on this host to use as target_repo.

    The factory is its own first target, so the repository root is a sensible
    worker-host path that exists.  US3-S1 and S2 test that a relative path is
    resolved to absolute; they do not need a separate target clone.
    """
    return str(Path(__file__).resolve().parents[3])


def _args(**overrides: Any) -> argparse.Namespace:
    defaults = {
        "spec_dir": str(FIXTURE),
        "target_repo": _existing_target_repo(),
        "specs_root": "specs",
        "output": None,
        "delta": False,
        "as_json": False,
    }
    return argparse.Namespace(**{**defaults, **overrides})


def _artifact(spec_dir: Path, output: Path | None = None) -> Path:
    if output is not None:
        return output
    return spec_dir / "workgraph.json"


def _load(artifact: Path) -> WorkGraph:
    document = json.loads(artifact.read_text(encoding="utf-8"))
    return WorkGraph(
        epic_id=document["epic_id"],
        feature=document["feature"],
        specs_root=document["specs_root"],
        target_repo=document["target_repo"],
        nodes=[],
    )


def test_derive_writes_absolute_specs_root(tmp_path: Path) -> None:
    """US3-S1: a relative specs root is stored as an absolute path.

    Which absolute path changed on 2026-08-26: an un-overridden default used to
    resolve `"specs"` against the CWD, which is correct only when the operator
    stands in the repo being built — in the demo container (WORKDIR
    /opt/ergane) it compiled `specs_root=/opt/ergane/specs` for a spec in
    /home/ergane/repo, and every dispatch was refused at prompt assembly. The
    default now follows the spec directory itself; this test pinned the old
    resolution and held US3-S1's real claim (absoluteness) at the same time.
    tests/test_derive_specs_root_default.py owns the resolution contract.
    """
    output = tmp_path / "workgraph.json"
    args = _args(
        spec_dir=str(FIXTURE),
        specs_root="specs",
        output=str(output),
    )
    assert derive_command(args) == 0

    graph = _load(output)
    assert Path(graph.specs_root).is_absolute()
    assert graph.specs_root == str(FIXTURE.parent)


def test_derive_writes_absolute_target_repo(tmp_path: Path) -> None:
    """US3-S2: the target repo is stored as an absolute path."""
    output = tmp_path / "workgraph.json"
    rel_repo = tmp_path / "repo"
    rel_repo.mkdir()
    args = _args(
        spec_dir=str(FIXTURE),
        target_repo=str(rel_repo),
        output=str(output),
    )
    assert derive_command(args) == 0

    graph = _load(output)
    assert Path(graph.target_repo).is_absolute()
    assert graph.target_repo == str(rel_repo.resolve())


def test_load_refuses_relative_path_before_key_mint(tmp_path: Path) -> None:
    """US3-S3: a relative path is refused at read time, naming field and value."""
    artifact = tmp_path / "workgraph.json"
    graph = WorkGraph(
        epic_id="042-short-links",
        feature="042-short-links",
        specs_root="specs",
        target_repo="/home/admin/code/ergane-target",
        nodes=[],
    )
    artifact.write_text(json.dumps(asdict(graph), indent=2) + "\n", encoding="utf-8")

    with pytest.raises(WorkGraphError) as caught:
        load_workgraph(artifact)
    message = str(caught.value)
    assert "specs_root" in message
    assert "specs" in message


def test_derive_reports_missing_specs_root_as_resolved_absolute_path(
    tmp_path: Path,
) -> None:
    """US3-S4: a missing specs root fails naming the resolved absolute path."""
    # Supply a relative path so resolution changes the string.  `tmp_path` is
    # absolute, so construct a relative segment that resolves against cwd.
    missing = Path("no-such-specs-tmp")
    resolved = missing.resolve()
    args = _args(
        spec_dir=str(FIXTURE),
        specs_root=str(missing),
    )

    # _OperatorError is the internal exception; the public noun layer translates
    # it to an OperatorError the CLI renders.  Capturing the public layer proves
    # the message reaches the operator.
    from factory.cli.nouns.spec import _derive_command
    from factory.cli.errors import OperatorError

    with pytest.raises(OperatorError) as caught:
        _derive_command(args)
    message = str(caught.value)
    assert str(resolved) in message
    assert str(resolved) != str(missing)
    assert Path(str(resolved)).is_absolute()
