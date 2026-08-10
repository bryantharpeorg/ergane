"""Noun registration for `ergane roadmap`."""

from __future__ import annotations

from factory.cli.nouns import Noun
from factory.cli.roadmap import add_roadmap_parser

NOUN = Noun(
    name="roadmap",
    summary="run and steer the roadmap scheduler",
    order=50,
    add_parser=add_roadmap_parser,
)
