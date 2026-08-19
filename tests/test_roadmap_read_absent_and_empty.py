"""US2: a missing or empty `specs/` root returns an empty roadmap.

The reporter measured `{"Total": 4, "SkippedOverlap": 3}` because a fresh
`ergane init` produced no `specs/` directory, and the roadmap workflow's first
read of an absent root raised.  US2 adds these cells, while preserving the
docstring's loud-failure discipline for malformed corpuses (trap 5): absent
and empty are *not* malformed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from factory.roadmap.models import RoadmapError, read_roadmap


def test_missing_root_returns_empty_roadmap(tmp_path: Path) -> None:
    """US2-S1 / FR-005: a specs root that does not exist is an empty corpus."""
    missing = tmp_path / "nonexistent" / "specs"
    assert not missing.exists()

    roadmap = read_roadmap(missing)

    assert roadmap.entries == []
    assert roadmap.specs_root == str(missing)


def test_existing_empty_root_returns_empty_roadmap(tmp_path: Path) -> None:
    """US2-S2: an existing, empty specs root returns an empty roadmap.

    This cell already worked and must keep working: a test that omits it cannot
    detect a reader that now returns empty for everything (trap 2).
    """
    empty_root = tmp_path / "specs"
    empty_root.mkdir()

    roadmap = read_roadmap(empty_root)

    assert roadmap.entries == []
    assert roadmap.specs_root == str(empty_root)


def test_malformed_corpus_still_raises_naming_every_fault(tmp_path: Path) -> None:
    """US2-S3 / FR-006: a malformed corpus still raises, naming every fault.

    A missing root is empty; a malformed root is still loud. The reader must
    continue to emit nothing on failure so a partial roadmap never escapes.
    """
    specs_root = tmp_path / "specs"
    bad_spec = specs_root / "001-x"
    bad_spec.mkdir(parents=True)
    bad_spec.joinpath("spec.md").write_text(
        "---\nstate: ready\npriority: P1\n---\n", encoding="utf-8"
    )

    with pytest.raises(RoadmapError) as caught:
        read_roadmap(specs_root)

    findings = list(caught.value.findings)
    assert len(findings) == 1
    assert findings[0].rule == "unknown_key"
    assert "priority" in str(findings[0])
    assert "001-x" in str(findings[0])


def test_root_that_is_a_file_is_distinguished(tmp_path: Path) -> None:
    """Edge case: a root that exists but is a file is none of absent/empty/malformed.

    The contract names three distinct states; a file masquerading as a specs
    root must not silently read as empty.
    """
    file_root = tmp_path / "specs"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(Exception) as caught:
        read_roadmap(file_root)

    # `iterdir()` raises NotADirectoryError (a subclass of OSError), not a
    # generic catch-all.  This test pins the real, narrow error rather than a
    # swallowed empty return.
    assert isinstance(caught.value, (NotADirectoryError, OSError))
