"""Noun registration for `ergane status`.

Ordered just after `spec` and before `build`: it is the verb an operator reaches
for before either of the per-object views, and the bare `ergane` listing is read
top to bottom.
"""

from __future__ import annotations

from factory.cli.nouns import Noun
from factory.cli.status import add_status_parser

NOUN = Noun(
    name="status",
    summary="what the whole floor is doing right now",
    order=25,
    add_parser=add_status_parser,
)
