"""An un-overridden `--specs-root` follows the spec, not the working directory.

`specs_root` + `feature` are what resolve the authored trio at dispatch
(models.py: "`specs_root` + `feature` resolve the spec that criteria are
snapshotted from"). Resolving the default `"specs"` against the process CWD is
correct only when the operator stands in the repository being built — which is
always true on the floor, and is why this went unnoticed.

It stops being true the moment the CLI is not run from the repo it builds. In
the demo container the working directory is the IMAGE root, so

    ergane build ship /home/ergane/repo/specs/001-demo \
        --target-repo /home/ergane/repo --yes --halt-after-pass

compiled a graph carrying `specs_root: '/opt/ergane/specs'` — the CLI's own
tree — and the prompt-assembly preflight refused the dispatch with

    cannot read /opt/ergane/specs/001-demo/spec.md: [Errno 2] ...

for all three trio documents, while `target_repo` was correctly
`/home/ergane/repo`. Measured 2026-08-26, the sixth defect found by running the
demo stack.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from factory.cli.main import main as ergane_main

# The demo's own generated spec, trimmed. Using the shape `scaffold_spec(
# demonstration=True)` emits is deliberate: this defect is about the demo's
# dispatch, so the fixture should be the text the demo actually compiles.
SPEC = """---
state: draft
---

# Feature Specification: demo

A throwaway demonstration spec carrying one worked story.

### User Story 1 - Demonstration (Priority: P1)

As a developer reading my first scaffold, I see a worked story slot for US1.

**Acceptance Scenarios**:

1. **Given** a scaffolded project, **When** the demo dispatches it, **Then** one
   node is compiled and handed a prompt.

**Why this priority**: Core teaching story

**Independent Test**: Verify the scaffold structure parses cleanly.

## Functional Requirements

- **FR-001**: The system MUST support the worked story `demo`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
"""

PLAN = "# Plan\n\nDo the thing.\n"
TASKS = "# Tasks\n\n- [ ] T001 [US1] do the thing\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A target repo whose specs live somewhere the CWD will not point at."""
    spec_dir = tmp_path / "repo" / "specs" / "001-demo"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC, encoding="utf-8")
    (spec_dir / "plan.md").write_text(PLAN, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS, encoding="utf-8")
    return tmp_path / "repo"


def _derive(repo: Path, *extra: str) -> dict:
    spec_dir = repo / "specs" / "001-demo"
    code = ergane_main(
        ["spec", "derive", str(spec_dir), "--target-repo", str(repo), *extra]
    )
    assert code == 0, "derive should succeed"
    document = json.loads((spec_dir / "workgraph.json").read_text(encoding="utf-8"))
    return document.get("graph", document)


def test_specs_root_follows_the_spec_when_the_cwd_is_elsewhere(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container's exact shape: CWD is not the repo being built."""
    elsewhere = tmp_path / "image-root"
    (elsewhere / "specs").mkdir(parents=True)  # a decoy, as /opt/ergane/specs was
    monkeypatch.chdir(elsewhere)

    graph = _derive(repo)

    assert graph["specs_root"] == str(repo / "specs"), (
        "specs_root must name the target repo's specs directory, not the one under "
        f"the working directory ({elsewhere / 'specs'})"
    )
    assert graph["target_repo"] == str(repo)
    assert Path(graph["specs_root"], graph["feature"], "spec.md").is_file(), (
        "the resolved trio path must actually exist — this is what dispatch reads"
    )


def test_the_floor_s_own_shape_is_unchanged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Standing in the repo, the old CWD-relative default gave the same answer.

    This is the compatibility claim the fix rests on: on the floor an operator
    runs `ergane spec derive specs/<dir> --target-repo $PWD` from the repo root,
    where `Path("specs").resolve()` and `spec_dir.parent` are the same path.
    """
    monkeypatch.chdir(repo)

    graph = _derive(repo)

    assert graph["specs_root"] == str(Path(os.getcwd()) / "specs")
    assert graph["specs_root"] == str(repo / "specs")


def test_an_explicit_specs_root_still_wins(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The split-host topology: the worker's path is not the CLI's.

    Whoever passes `--specs-root` is asserting a worker-host fact the CLI cannot
    check, and the fix must not quietly override it.
    """
    monkeypatch.chdir(tmp_path)
    worker_side = tmp_path / "worker-view" / "specs"
    worker_side.mkdir(parents=True)

    graph = _derive(repo, "--specs-root", str(worker_side))

    assert graph["specs_root"] == str(worker_side)
