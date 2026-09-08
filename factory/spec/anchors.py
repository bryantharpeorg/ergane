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


def _check_anchor_resolution(
    spec_dir: Path,
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> None:
    """Report every `path:NN` and `path:NN-MM` citation that does not resolve.

    Citations are read from the body of `spec.md` (frontmatter skipped),
    `plan.md`, and `tasks.md`. Citations inside fenced code blocks are ignored
    by reusing the criteria parser's fence mask. Paths are resolved against the
    target repository the command was given. When that repository cannot be read,
    the layer reports itself as skipped and produces no findings (FR-011).
    """
    target_root = Path(target_repo)

    docs: dict[str, str] = {}
    for name in ("plan.md", "tasks.md"):
        path = spec_dir / name
        try:
            docs[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # An absent authored document has no citations, per trap 9.
            continue

    # spec.md body, not frontmatter.
    _, body = _split_frontmatter(spec_text)
    if body:
        docs["spec.md"] = body

    if not docs:
        # Nothing to scan, but the layer still ran.
        checked.append("anchor_resolution")
        return

    # Collect citations with their line numbers first, then read each file once.
    #
    # A bare `:NN` reference carries the most recently cited *path* forward within
    # the same markdown section. "Section" is bounded by a markdown heading (any
    # line starting with one or more `#` characters): that is wide enough for a
    # trap several paragraphs below its path (068's traps 3 and 4) and narrow
    # enough that a heading change is a deliberate context switch. A bullet alone
    # is too narrow — a path in one bullet should still resolve a bare reference in
    # the prose or bullets that follow under the same heading (trap 3).
    citations: list[tuple[str, int, str, str, int]] = []
    # Ranges written backwards. Held apart because they are decidable without
    # opening anything, but they are still this layer's findings and so are
    # withheld with the rest when the layer skips.
    inverted: list[tuple[str, int, str, int, int]] = []
    # Bare `:NN` or `:NN-MM` references that cannot be resolved in their section.
    unanchored: list[tuple[str, int, str]] = []
    cited_paths: set[str] = set()
    for doc_name, text in docs.items():
        lines = text.splitlines()
        in_code = mask_fences(lines)
        current_path: str | None = None
        for index, line in enumerate(lines, start=1):
            if in_code[index - 1]:
                continue
            # A heading starts a new section, so any bare reference after it must
            # find a path *below* that heading, not one carried from above.
            if line.lstrip().startswith("#"):
                current_path = None
                continue
            # Resolve bare references first, before this line's own path citation
            # updates the carrier. A bare `:NN` on the same line as a `path:NN` is
            # governed by the path on that line or an earlier one, not by itself.
            bare_match = _BARE_LINE_RE.search(line)
            if bare_match:
                bare_raw = bare_match.group(1)
                if "-" in bare_raw:
                    try:
                        bare_start = int(bare_raw.split("-", 1)[0])
                        bare_end = int(bare_raw.split("-", 1)[1])
                    except ValueError:
                        pass
                    else:
                        if current_path is None:
                            unanchored.append((doc_name, index, bare_match.group(0)))
                        else:
                            citation = f"{current_path}:{bare_raw}"
                            cited_paths.add(current_path)
                            if bare_end < bare_start:
                                inverted.append((doc_name, index, citation, bare_start, bare_end))
                            citations.append((doc_name, index, current_path, citation, bare_start))
                            citations.append((doc_name, index, current_path, citation, bare_end))
                else:
                    try:
                        bare_line = int(bare_raw)
                    except ValueError:
                        pass
                    else:
                        if current_path is None:
                            unanchored.append((doc_name, index, bare_match.group(0)))
                        else:
                            citation = f"{current_path}:{bare_raw}"
                            cited_paths.add(current_path)
                            citations.append((doc_name, index, current_path, citation, bare_line))
            for match in _ANCHOR_RE.finditer(line):
                citation = match.group(1)
                if ":" not in citation:
                    continue
                raw_path, raw_lines = citation.rsplit(":", 1)
                # Update the carrier *after* resolving any bare reference on this
                # line, so a path cited on line N governs a bare `:NN` on line N.
                current_path = raw_path
                if "-" in raw_lines:
                    try:
                        start_line, end_line = raw_lines.split("-", 1)
                        start_int = int(start_line)
                        end_int = int(end_line)
                    except ValueError:
                        continue
                    cited_paths.add(raw_path)
                    # FR-005: both endpoints are checked, and a range that runs
                    # backwards is reported on its own account — a span whose
                    # end precedes its start names no lines at all, so neither
                    # endpoint resolving would otherwise say anything.
                    if end_int < start_int:
                        inverted.append((doc_name, index, citation, start_int, end_int))
                    citations.append((doc_name, index, raw_path, citation, start_int))
                    citations.append((doc_name, index, raw_path, citation, end_int))
                else:
                    try:
                        line_int = int(raw_lines)
                    except ValueError:
                        continue
                    cited_paths.add(raw_path)
                    citations.append((doc_name, index, raw_path, citation, line_int))

    if not citations and not unanchored:
        checked.append("anchor_resolution")
        return

    # FR-010: a refusal only for a spec that can still dispatch. The 998 broken
    # anchors in landed specs are reported, but they do not fail a validate.
    severity = _severity_for_state(_spec_state(spec_text))

    # A range is two entries against one citation, so an absent file would
    # otherwise be reported twice for the same anchor. FR-004 wants the citation
    # named, not counted.
    said: set[str] = set()

    def report(message: str) -> None:
        if message in said:
            return
        said.add(message)
        findings.append(_ValidateFinding("anchor_resolution", message, severity=severity))

    for doc_name, citing_line, citation, start_int, end_int in inverted:
        report(
            f"{doc_name}:{citing_line}: `{citation}` is a range whose end "
            f"({end_int}) precedes its start ({start_int})"
        )

    # FR-009: unanchored bare references are reported even when no file can be
    # opened. They name no path, so the target-repo skip does not apply to them.
    for doc_name, citing_line, bare_text in unanchored:
        report(
            f"{doc_name}:{citing_line}: {bare_text} is unanchorable: no path was cited "
            "before it in the same section"
        )

    if not citations:
        checked.append("anchor_resolution")
        return

    contents = _read_citation_files(target_root, cited_paths)
    any_readable = any(lines is not None for lines in contents.values())
    if not any_readable:
        # FR-011: when *none* of the cited files can be read, the tree the
        # command was given is not the tree the specs cite. Skip the whole layer
        # rather than report every citation as an absent file — validate's
        # `--target-repo` default is a path most hosts do not carry, and a layer
        # that refuses instead of skipping turns every spec into a wall of false
        # refusals (trap 11).
        reason = (
            f"target repository {target_repo} is not a readable directory"
            if not target_root.is_dir()
            else f"none of the cited paths exist under target repository {target_repo}"
        )
        skipped.append({"layer": "anchor_resolution", "reason": reason})
        return

    for doc_name, citing_line, raw_path, citation, line_no in citations:
        file_lines = contents.get(raw_path)
        if file_lines is None:
            # A cited file that does not exist is a finding, even when some
            # other cited files could be read (FR-011 says skip only when the
            # tree as a whole cannot be read).
            report(
                f"{doc_name}:{citing_line}: `{citation}` points at absent file `{raw_path}`"
            )
        elif line_no < 1 or line_no > len(file_lines):
            report(
                f"{doc_name}:{citing_line}: `{citation}` line {line_no} is past end of file "
                f"({len(file_lines)} lines in `{raw_path}`)"
            )
        elif file_lines[line_no - 1].strip() == "":
            report(
                f"{doc_name}:{citing_line}: `{citation}` line {line_no} is blank in `{raw_path}`"
            )

    checked.append("anchor_resolution")
