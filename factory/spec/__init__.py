"""The typed validation policy: the report `ergane spec validate` renders.

US1 of 133 plants the shared floor the rest of the spec relocates onto: the
finding type every layer body constructs and the report that carries the four
channels the verb prints. Nothing here imports from
`factory.cli.nouns.spec` — the import direction is one-way from US1 onward,
because the CLI module's import block ends above every name it binds, so an
import back re-enters a half-initialised module and raises `ImportError` at
interpreter start (plan trap 17). A body that needs a CLI-module name means
that name moves here instead.

US2 relocates the first two layer bodies into the package: the anchor
family — `anchor_resolution` and `symbol_anchors` (072-US1/072-US2) — with the
module-level grammars they alone read (`_ANCHOR_RE`, `_BARE_LINE_RE`,
`_SYMBOL_ANCHOR_RE`, `_DISPATCHABLE_STATES`). The names are re-exported here so
the CLI module binds them under their old private spellings with one import.
"""

from __future__ import annotations

from factory.spec.report import SpecFinding, SpecValidation
from factory.spec.anchors import (
    _ANCHOR_RE,
    _BARE_LINE_RE,
    _DISPATCHABLE_STATES,
    _SYMBOL_ANCHOR_RE,
    _check_anchor_resolution,
    _check_symbol_anchors,
    _line_hits_symbol,
    _read_citation_files,
    _severity_for_state,
    _spec_state,
    _symbol_spans,
)

__all__ = [
    "SpecFinding",
    "SpecValidation",
    "anchors",
    "check_anchor_resolution",
    "check_symbol_anchors",
    "line_hits_symbol",
    "read_citation_files",
    "severity_for_state",
    "spec_state",
    "symbol_spans",
]

# The private spellings the CLI module binds back under are re-bound here as
# well: T013 asserts the CLI's binding *is* the object defined in factory.spec,
# and identity is cheapest to prove when both sides re-export from one module.
check_anchor_resolution = anchors._check_anchor_resolution
check_symbol_anchors = anchors._check_symbol_anchors
line_hits_symbol = anchors._line_hits_symbol
read_citation_files = anchors._read_citation_files
severity_for_state = anchors._severity_for_state
spec_state = anchors._spec_state
symbol_spans = anchors._symbol_spans