"""The anchor layers' shared vocabulary and the symbol-anchor checker (072's tier).

US2 of 133 moves the symbol tier out of `factory/cli/nouns/spec.py`: the
citation grammar, the state/severity helpers both anchor tiers read, the
citation-file reader, and the four module-level names. `_check_anchor_resolution`
still runs in the CLI module until US7, and it reads `_spec_state` and
`_severity_for_state` from here through the import-back, so those two are
shared vocabulary, not symbol-tier internals.

Nothing here imports from `factory.cli.nouns.spec` (plan trap 17): the CLI
module imports from `factory.spec` at module scope, so an import back re-enters
a half-initialised module before its names exist. A moved body that needs a
CLI-module name means that name moves too.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

from factory.roadmap.models import _split_frontmatter
from factory.verify.criteria import mask_fences
from factory.workgraph.prompt import TASKS_DOCUMENT

from factory.spec import SpecFinding as _ValidateFinding

#: A citation inside an inline code span: `path:NN` or `path:NN-MM`.
_ANCHOR_RE = re.compile(r"`([^`]+?:\d+(?:-\d+)?)`")

#: A bare line reference inside an inline code span: `:NN` or `:NN-MM`.
_BARE_LINE_RE = re.compile(r"`:(\d+(?:-\d+)?)`")


#: A citation written as `path.py:NN` — `symbol` or `path.py:NN` -- `symbol`.
#: Group 1 is the path, group 2 is the line number, group 3 is the symbol name.
_SYMBOL_ANCHOR_RE = re.compile(
    r"`([^`\n]+\.py):(\d+)`\s*[-–—]{1,2}\s*`([^`\n]+)`"
)

#: States that can still dispatch; anchor findings for these are refusals.
_DISPATCHABLE_STATES = {"draft", "ready"}


def _spec_state(spec_text: str) -> str | None:
    """The declared state from frontmatter, or None when there is none."""
    block_text, _body = _split_frontmatter(spec_text)
    if block_text is None:
        return None
    try:
        loaded = yaml.safe_load(block_text)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    state = loaded.get("state")
    return state if isinstance(state, str) else None


def _severity_for_state(state: str | None) -> str:
    """Refusal for dispatchable states, advisory otherwise (072 FR-010)."""
    if state in _DISPATCHABLE_STATES:
        return "refusal"
    return "advisory"


def _symbol_spans(module_text: str) -> dict[str, list[tuple[int, int]]]:
    """Map each defined name to its 1-indexed line-span ranges.

    Names are resolved from `FunctionDef`, `AsyncFunctionDef` and `ClassDef`
    nodes using `lineno` and `end_lineno`.  A dotted citation is resolved on
    its last segment: `Widget.do_thing` is accepted if `do_thing` is defined
    inside a class named `Widget`.
    """
    try:
        tree = ast.parse(module_text)
    except SyntaxError:
        return {}

    by_name: dict[str, list[tuple[int, int]]] = {}
    class_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_names.add(node.name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # `end_lineno` may be None in very old Python versions; the runtime
            # here is 3.12, but the defensive value keeps the type narrow.
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            by_name.setdefault(node.name, []).append((node.lineno, end))

    return by_name, class_names


def _line_hits_symbol(
    line: int, symbol: str, spans: dict[str, list[tuple[int, int]]], class_names: set[str]
) -> tuple[bool, str | None]:
    """True when `line` falls inside any definition of `symbol`.

    For a dotted name the last segment must have a span and the first segment
    must name a class.  A duplicate definition is satisfied by any matching
    span.
    """
    parts = symbol.split(".")
    root = parts[0] if len(parts) > 1 else None
    name = parts[-1]

    if root is not None and root not in class_names:
        # The first segment does not name a class; treat as absent so the
        # operator sees a distinct repair.
        return False, None

    ranges = spans.get(name, [])
    if not ranges:
        return False, "absent"

    for start, end in ranges:
        if start <= line <= end:
            return True, None

    # Outside every span: report the first known span as the actual location.
    actual = ranges[0]
    return False, f"{actual[0]}-{actual[1]}"


def _check_symbol_anchors(
    spec_dir: Path,
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> None:
    """Report backticked Python citations whose cited line is outside the named symbol's span.

    The convention is `` `path.py:NN` — `symbol` `` or `` `path.py:NN` -- `symbol` ``.
    A citation with no symbol name in its prose is left to the resolution check
    (072-US1).  Paths are resolved against `target_repo`; an unreadable target
    repo causes the whole layer to be skipped rather than reporting every
    citation as an absent file (072 FR-011).
    """
    target_path = Path(target_repo)
    if not target_path.is_dir():
        skipped.append(
            {
                "layer": "symbol_anchors",
                "reason": f"target repository {target_repo} is not a readable directory",
            }
        )
        return

    severity = _severity_for_state(_spec_state(spec_text))
    layer_ran = False

    # Read the authored documents, masking fenced blocks and spec.md frontmatter.
    documents: list[tuple[str, str]] = []
    for name in ("spec.md", "plan.md", TASKS_DOCUMENT):
        path = spec_dir / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if name == "spec.md":
            _block, text = _split_frontmatter(text)
        documents.append((name, text))

    if not documents:
        # No authored documents were read; nothing to check.
        return

    layer_ran = True

    # Cache: one AST parse per cited path, and one file read per path.
    file_cache: dict[str, str | None] = {}
    span_cache: dict[str, tuple[dict[str, list[tuple[int, int]]], set[str]] | None] = {}

    for doc_name, doc_text in documents:
        lines = doc_text.splitlines()
        in_code = mask_fences(lines)
        for line_no, line in enumerate(lines, start=1):
            if in_code[line_no - 1]:
                continue
            for match in _SYMBOL_ANCHOR_RE.finditer(line):
                cited_path = match.group(1)
                cited_line = int(match.group(2))
                symbol = match.group(3)

                full_path = target_path / cited_path
                path_key = str(full_path)

                if path_key not in file_cache:
                    try:
                        file_cache[path_key] = full_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        file_cache[path_key] = None

                module_text = file_cache[path_key]
                if module_text is None:
                    # The file is absent or unreadable; leave that to US1's
                    # resolution check rather than double-reporting here.
                    continue

                if path_key not in span_cache:
                    span_cache[path_key] = _symbol_spans(module_text)

                cached = span_cache[path_key]
                if cached is None:
                    # Syntax error: the layer cannot answer for this file.
                    continue

                spans, class_names = cached
                hit, reason = _line_hits_symbol(cited_line, symbol, spans, class_names)
                if hit:
                    continue

                if reason == "absent":
                    message = (
                        f"{doc_name}:{line_no}: `cited symbol {symbol}` in "
                        f"{cited_path}:{cited_line} is not defined in that file"
                    )
                elif reason is not None:
                    message = (
                        f"{doc_name}:{line_no}: {cited_path}:{cited_line} cites "
                        f"`{symbol}` which actually occupies lines {reason}"
                    )
                else:
                    # Dotted root did not name a class; report as absent symbol.
                    message = (
                        f"{doc_name}:{line_no}: `cited symbol {symbol}` in "
                        f"{cited_path}:{cited_line} is not defined in that file"
                    )

                findings.append(_ValidateFinding("symbol_anchors", message, severity=severity))

    if layer_ran:
        checked.append("symbol_anchors")


def _read_citation_files(target_repo: Path, paths: set[str]) -> dict[str, list[str] | None]:
    """Read every cited file once; None means the file could not be read."""
    contents: dict[str, list[str] | None] = {}
    for relative in paths:
        path = target_repo / relative
        try:
            contents[relative] = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            contents[relative] = None
    return contents
