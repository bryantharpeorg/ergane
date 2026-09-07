"""130-US1: a read-only-looking verb does not write.

`ergane spec derive --json` with no output path printed the compiled graph and
then unconditionally rewrote `<spec-dir>/workgraph.json` — the write sat before
`--json` was ever consulted. From an operator checkout whose `--target-repo`
differs from a committed artifact's, that rewrote the `target_repo` dispatch
reads, which is how 064's and 073's committed graphs were poisoned.

Five tests pin the boundary (FR-001, FR-002, FR-003, FR-011):

- US1-S1 the seeded bytes survive a `--json` run with no output path. The seed
  is the point: deriving and re-deriving compares one deterministic output
  against itself and passes against today's unconditional write, so the
  artifact is seeded with a `target_repo` this invocation would not derive and
  must still be on disk afterwards — bytes and mtime both, because a rewrite
  with identical bytes would pass a bytes-only check.
- US1-S2 an explicit `-o` is a request to persist — `--json` writes there.
- US1-S3 without `--json` the artifact is written exactly as today: 97
  committed artifacts are in the tree and the dispatch path reads one off disk.
- US1-S4 the printed document names no artifact, because none was written.
- US1-S5 `build ship --json` still reaches its summary — the FR-001 guard must
  not deny a caller that requires the artifact on disk, which is why ship asks
  for the write by path on a copy of its namespace.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main as ergane_main
from factory.workgraph.cli import ARTIFACT_NAME
from tests.test_ergane_build_ship import _make_spec_dir, _run_ship_command, _target_repo

#: The harm the ledger row records: a committed artifact whose `target_repo`
#: names a repository this invocation would never derive. Every test seeds this
#: before the verb runs; deriving and re-deriving would compare the output
#: against itself and prove nothing.
SEEDED_TARGET_REPO = "/srv/factory/targets/some-other-repo"

SEEDED_ARTIFACT = (
    "{"
    '"epic_id": "ship-demo", "feature": "ship-demo", '
    '"specs_root": "/elsewhere/specs", '
    f'"target_repo": "{SEEDED_TARGET_REPO}", '
    '"nodes": [], "inferred_edges": []'
    "}\n"
)


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        return ergane_main(list(argv))
    except SystemExit as exit_request:
        return 0 if exit_request.code is None else int(exit_request.code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _seeded_spec_dir(tmp_path: Path) -> tuple[Path, Path]:
    """A sound spec directory whose committed artifact names another repo."""
    spec_dir = _make_spec_dir(tmp_path)
    (spec_dir / ARTIFACT_NAME).write_text(SEEDED_ARTIFACT, encoding="utf-8")
    return spec_dir, _target_repo(tmp_path)


# --- US1-S1 / FR-001: the verb prints and persists nothing --------------------


def test_derive_json_without_output_path_leaves_seeded_bytes_on_disk(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    spec_dir, target_repo = _seeded_spec_dir(tmp_path)
    artifact = spec_dir / ARTIFACT_NAME
    bytes_before = artifact.read_bytes()
    mtime_before = artifact.stat().st_mtime_ns

    result = run(
        "spec", "derive", "--json", str(spec_dir), "--target-repo", str(target_repo)
    )

    assert result.code == 0
    # The invocation would derive its own target repo — the seed is not what
    # this call would write, so a surviving seed is a skipped write, not a
    # no-op rewrite.
    doc = result.json
    assert doc["graph"]["target_repo"] != SEEDED_TARGET_REPO
    # The seeded bytes, and only them, are still the file's bytes — and the
    # file was not even touched, which a same-bytes rewrite would hide.
    assert artifact.read_bytes() == bytes_before
    assert artifact.stat().st_mtime_ns == mtime_before
    assert SEEDED_TARGET_REPO.encode() in artifact.read_bytes()


# --- US1-S2 / FR-002: an explicit output path is a request to persist --------


def test_derive_json_with_output_path_writes_there(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    spec_dir, target_repo = _seeded_spec_dir(tmp_path)
    out = tmp_path / "compiled-elsewhere.json"

    result = run(
        "spec",
        "derive",
        "--json",
        "-o",
        str(out),
        str(spec_dir),
        "--target-repo",
        str(target_repo),
    )

    assert result.code == 0
    doc = result.json
    assert doc["artifact"] == str(out)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["epic_id"] == "ship-demo"
    assert written["target_repo"] != SEEDED_TARGET_REPO
    # The seeded artifact is not where the graph went: the explicit path was.
    assert (spec_dir / ARTIFACT_NAME).read_text(encoding="utf-8") == SEEDED_ARTIFACT


# --- US1-S3 / FR-002: without --json the artifact is written exactly as today -


def test_derive_without_json_still_writes_the_artifact(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    spec_dir, target_repo = _seeded_spec_dir(tmp_path)

    result = run("spec", "derive", str(spec_dir), "--target-repo", str(target_repo))

    assert result.code == 0
    artifact = spec_dir / ARTIFACT_NAME
    written = json.loads(artifact.read_text(encoding="utf-8"))
    assert written["epic_id"] == "ship-demo"
    assert written["target_repo"] != SEEDED_TARGET_REPO
    assert result.stdout.rstrip().endswith(str(artifact))


# --- US1-S4 / FR-003: the document names no artifact it did not write ---------


def test_derive_json_document_carries_no_artifact_path(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    spec_dir, target_repo = _seeded_spec_dir(tmp_path)

    result = run(
        "spec", "derive", "--json", str(spec_dir), "--target-repo", str(target_repo)
    )

    assert result.code == 0
    doc = result.json
    # Nothing was written, so the document must not name a file at all: a
    # consumer parsing the key would follow it to a file that is absent or,
    # worse, the stale seeded one.
    assert "artifact" not in doc


# --- US1-S5 / FR-011: ship --json still finds the artifact --------------------


def test_ship_with_json_still_resolves_the_artifact_and_reaches_its_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The FR-001 guard must not deny a caller that requires the file on disk.

    Ship's own parser declares `--json` with `dest="as_json"` and no output
    path, so ship presents to the derive handler as exactly the shape FR-001
    denies — and then demands the artifact at stage 3. A guard keyed on
    `--json` alone fails this test with "derive reported success but wrote no
    artifact"; ship instead asks for the write by path.
    """
    spec_dir = _make_spec_dir(tmp_path)
    target_repo = _target_repo(tmp_path)
    calls: list[argparse.Namespace] = []

    result = _run_ship_command(
        monkeypatch,
        "--json",
        "--yes",
        spec_dir=spec_dir,
        target_repo=target_repo,
        start_stub=lambda args: (calls.append(args) or 0),
    )

    assert result.code == 0
    assert "ship: compiled graph" in result.stdout
    assert (spec_dir / ARTIFACT_NAME).is_file()
    assert len(calls) == 1