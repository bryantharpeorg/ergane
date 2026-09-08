"""The typed validation policy: the report `ergane spec validate` renders.

US1 of 133 plants the shared floor the rest of the spec relocates onto: the
finding type every layer body constructs and the report that carries the four
channels the verb prints. Nothing here imports from
`factory.cli.nouns.spec` — the import direction is one-way from US1 onward,
because the CLI module's import block ends above every name it binds, so an
import back re-enters a half-initialised module and raises `ImportError` at
interpreter start (plan trap 17). A body that needs a CLI-module name means
that name moves here instead.
"""

from __future__ import annotations

# The report import is first, deliberately: every relocated module binds its
# finding type with `from factory.spec import SpecFinding`, and the eager
# composition import below pulls those modules in while this package is still
# initialising — `SpecFinding` must already be bound here when they ask.
from factory.spec.report import SpecFinding, SpecValidation

from factory.spec.composition import SpecReadError, validate_spec

__all__ = [
    "SpecFinding",
    "SpecValidation",
    "SpecReadError",
    "validate_spec",
]