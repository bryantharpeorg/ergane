"""Default floor text and resolver for `ergane init`.

The seeded constitution is the repository's document from the moment it is
written: generic principles, a project section the repository fills in, and a
governance section that says how to amend it. The floor text lives as package
data so an installed wheel carries it, and is resolved `importlib.resources`-first
after the pattern in `factory.config` (057 FR-005).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import NamedTuple

#: Basename of the shipped default floor file inside the package.
DEFAULT_FLOOR_FILENAME = "default_floor.md"


class FloorSource(NamedTuple):
    """Where a floor came from and what text to use."""

    path: str
    text: str


def shipped_floor_text() -> str:
    """Return the shipped default floor text, package data first.

    In an installed wheel the file travels inside the `factory` package via the
    `pyproject.toml` force-include entry. In a development checkout the source
    file lives at the repo root, so the same text is returned from there as a
    fallback.
    """
    packaged = importlib.resources.files("factory") / DEFAULT_FLOOR_FILENAME
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    # Development checkout fallback: the source file is at the repo root, not yet
    # packaged. The load path never falls back here; this is only for seeding.
    example_source = Path(__file__).resolve().parents[1] / DEFAULT_FLOOR_FILENAME
    return example_source.read_text(encoding="utf-8")


def resolve_default_floor() -> FloorSource:
    """Resolve the shipped default floor: package data first, checkout second."""
    packaged = importlib.resources.files("factory") / DEFAULT_FLOOR_FILENAME
    if packaged.is_file():
        return FloorSource(path=str(packaged), text=packaged.read_text(encoding="utf-8"))
    example_source = Path(__file__).resolve().parents[1] / DEFAULT_FLOOR_FILENAME
    return FloorSource(path=str(example_source), text=example_source.read_text(encoding="utf-8"))
