"""133-US2: the anchor and symbol layers leave the CLI module.

The two layers 072 added — `anchor_resolution` and `symbol_anchors` — move from
`factory/cli/nouns/spec.py` into `factory/spec/`, with the two module-level
regexes they alone read (`_ANCHOR_RE`, `_BARE_LINE_RE`) travelling with them
(plan trap 17: a moved body that needs a CLI-module name means the name moves
too, because the CLI module may never be imported back). The move is
mechanical: every refusal string and every parameter is unchanged, and the
checkers still accumulate into caller-owned `findings`, `skipped` and `checked`
lists rather than returning a report (plan trap 7). `_check_anchor_resolution`
still appends `anchor_resolution` to `checked` at each of its four exits (plan
trap 5) — hoisting them into one append at the caller would make the layer
report as checked on paths where today it does not (FR-005).

Red first. `uv run pytest tests/test_133_us2_anchor_layers_leave_the_cli_module.py
-q --no-header`, run against the tree as received — US1 landed, the anchor
family still defined in the CLI module — verbatim::

    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_cli_module_no_longer_defines_the_anchor_family
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_cli_module_calls_the_anchor_checkers_defined_in_factory_spec
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_factory_spec_defines_the_moved_names
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_moved_checkers_keep_their_parameters_and_append_into_caller_owned_lists
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::test_the_signatures_are_unchanged
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_1_no_documents
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_2_no_citations_found
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_3_citations_but_no_paths_cited
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_4_the_normal_end
    FAILED tests/test_133_us2_anchor_layers_leave_the_cli_module.py::TestAnchorResolutionCheckedAppends::test_exit_4_reports_stale_anchors_before_appending
    10 failed, 1 passed in 0.18s

The one that passed red is T012's second half — the eleven names still bound as
module attributes, which is true before the move and stays true after T016's
import back: it is the half of the definition/binding distinction the source
read enforces from the other side. T014's driven half (the four exits, the
caller-owned lists) is red only because `factory.spec.anchors` does not exist
yet; those five tests are the ones a rewrite would keep red and a pure move
turns green.
"""

from __future__ import annotations

import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every name the story moves, read from the CLI module's *source* rather than
#: as module attributes: an attribute check would also pass on an import, and
#: the import back is exactly what T016 lands (T012's own text says why — "by
#: reading the module source rather than by importing names that would still
#: resolve through the import").
CLI_MODULE_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"

#: The eleven names US2-S1 lists — the anchor family and the two grammars.
ANCHOR_FAMILY = (
    "_check_anchor_resolution",
    "_check_symbol_anchors",
    "_symbol_spans",
    "_line_hits_symbol",
    "_read_citation_files",
    "_spec_state",
    "_severity_for_state",
    "_SYMBOL_ANCHOR_RE",
    "_DISPATCHABLE_STATES",
    "_ANCHOR_RE",
    "_BARE_LINE_RE",
)

#: The checkers the CLI verb calls (US2-S4). The helpers and grammars the
#: checkers read are *not* in this tuple: a re-declaration of a helper would
#: not make the CLI call a foreign object, but a re-declared checker would.
ANCHOR_CHECKERS = (
    "_check_anchor_resolution",
    "_check_symbol_anchors",
)


def _cli_module_source() -> str:
    return CLI_MODULE_PATH.read_text(encoding="utf-8")


def _definition_lines(name: str, source: str) -> list[int]:
    """Lines of `source` that *define* `name` — a `def`, an assignment, or a
    decorated definition — rather than merely mention it."""
    lines: list[int] = []
    for index, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        is_def = stripped.startswith(f"def {name}(") and not stripped.startswith(
            f"def {name}_"
        )
        is_assign = stripped.startswith(f"{name} =") or stripped.startswith(
            f"{name}:"
        )
        # A decorated def carries the `@` on its own line; the `def` line below
        # it is matched by the `is_def` arm above.
        if is_def or is_assign:
            lines.append(index)
    return lines


# --- US2-S1 / FR-010: the CLI module defines none of the eleven names --------


def test_the_cli_module_no_longer_defines_the_anchor_family() -> None:
    """T012, US2-S1. Source-read, not attribute-read.

    An attribute check would also pass on the import T016 lands, so this reads
    the module's source for a `def` or an assignment — the same discipline
    US1's T005 used for `class _ValidateFinding`. Leaving any of the four
    grammars behind (`_SYMBOL_ANCHOR_RE`, `_DISPATCHABLE_STATES`, `_ANCHOR_RE`,
    `_BARE_LINE_RE`) makes the moved body reach back into the module it just
    left, which cannot import (plan trap 17).
    """
    source = _cli_module_source()
    for name in ANCHOR_FAMILY:
        lines = _definition_lines(name, source)
        assert lines == [], (
            f"factory/cli/nouns/spec.py still defines {name} at line(s) {lines}; "
            "the anchor family belongs in factory/spec (US2-S1, FR-010)"
        )


def test_the_cli_module_still_binds_the_moved_names() -> None:
    """T012's second half: the names still resolve, by import, not by definition.

    The CLI still composes — `_validate_command` calls
    `_check_anchor_resolution` and `_check_symbol_anchors` exactly as it does
    today (T016) — so the eleven names must still be reachable as module
    attributes. The distinction between "defined here" and "bound by import"
    is the whole of US2-S1, and the two assertions hold it from both sides.
    """
    import factory.cli.nouns.spec as spec_noun

    for name in ANCHOR_FAMILY:
        assert hasattr(spec_noun, name), (
            f"factory.cli.nouns.spec no longer binds {name}; "
            "the CLI still composes and needs the import back (T016)"
        )


# --- US2-S4 / FR-010: the CLI calls factory.spec's objects, not copies --------


def test_the_cli_module_calls_the_anchor_checkers_defined_in_factory_spec() -> None:
    """T013, US2-S4. `__module__` compared, not just names bound.

    A re-declaration inside `factory.spec` — or a second copy of the anchor
    grammar there — would pass T012 while being the exact duplication this
    spec exists to end (plan trap 17's last paragraph). Identity, not module
    equality alone: the object the CLI binds must be *the* object defined in
    `factory.spec`.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec

    for name in ANCHOR_FAMILY:
        mine = getattr(spec_noun, name)
        theirs = getattr(factory.spec, name)
        assert mine is theirs, (
            f"{name}: the CLI module's binding is not the object defined in "
            f"factory.spec ({mine!r} vs {theirs!r}) — a re-declaration cannot "
            "pass as a move (US2-S4)"
        )
        assert mine.__module__ == "factory.spec", (
            f"{name} reports __module__ {mine.__module__!r}, expected "
            "'factory.spec'"
        )


def test_factory_spec_defines_the_moved_names() -> None:
    """T012/T013's positive side: the eleven names are *defined* in factory.spec.

    Source-read the same way the CLI half is, so a factory.spec that only
    imports the names from somewhere else cannot pass: the bodies live here
    (FR-010 — "MUST be defined in `factory/spec/`").
    """
    from factory.spec import anchors

    source = Path(anchors.__file__).read_text(encoding="utf-8")
    for name in ANCHOR_FAMILY:
        assert _definition_lines(name, source), (
            f"factory/spec/anchors.py does not define {name}; an import of it "
            "from elsewhere is not the move FR-010 declares"
        )
    for name in ANCHOR_CHECKERS:
        assert getattr(anchors, name).__module__ == "factory.spec.anchors"


# --- US2-S2 / FR-010: the move changed no body, no parameter, no channel ------


def test_the_moved_checkers_keep_their_parameters_and_append_into_caller_owned_lists() -> None:
    """T014, US2-S2. Parameters unchanged; the lists stay caller-owned.

    Driven, not read: each checker is called with real lists and the assertion
    is on what it appends. A conversion to a returned report while moving would
    be the rewrite plan trap 7 forbids — it doubles the diff into trap 6's
    refusal and destroys the only cheap evidence that nothing changed.
    """
    from factory.spec import anchors

    findings: list = []
    skipped: list = []
    checked: list = []

    # A tmp target repo that is not a directory: `_check_symbol_anchors` skips
    # on `factory/cli/nouns/spec.py:897`'s guard, so the parameter contract is
    # exercised without reading any file at all.
    anchors._check_symbol_anchors(
        Path("no-such-spec-dir"), "state: draft\n", "no-such-target-repo", findings, skipped, checked
    )
    assert checked == []
    assert findings == []
    assert [entry["layer"] for entry in skipped] == ["symbol_anchors"]

    # The same call with a real directory and no authored documents: the layer
    # runs and checks nothing (the documents loop finds nothing to read).
    findings, skipped, checked = [], [], []
    anchors._check_symbol_anchors(
        Path("also-missing"), "state: draft\n", str(Path(__file__).parent), findings, skipped, checked
    )
    assert findings == []
    assert skipped == []

    # `_check_anchor_resolution` with no target repo: skip, not refusal.
    findings, skipped, checked = [], [], []
    anchors._check_anchor_resolution(
        Path("no-such-spec-dir"), "---\nstate: draft\n---\n# Spec\n", "no-such-target-repo", findings, skipped, checked
    )
    assert checked == []
    assert findings == []
    assert [entry["layer"] for entry in skipped] == ["anchor_resolution"]

    # Still no return value: both checkers accumulate and return None.
    assert anchors._check_symbol_anchors(
        Path("x"), "state: draft\n", "y", [], [], []
    ) is None
    assert anchors._check_anchor_resolution(
        Path("x"), "state: draft\n", "y", [], [], []
    ) is None


def _check_signatures_unchanged() -> None:
    """T014's static half: the parameter names, in order, per checker."""
    from factory.spec import anchors

    expected = {
        "_check_symbol_anchors": (
            "spec_dir", "spec_text", "target_repo", "findings", "skipped", "checked"
        ),
        "_check_anchor_resolution": (
            "spec_dir", "spec_text", "target_repo", "findings", "skipped", "checked"
        ),
        "_read_citation_files": ("target_repo", "paths"),
        "_spec_state": ("spec_text",),
        "_severity_for_state": ("state",),
        "_symbol_spans": ("module_text",),
        "_line_hits_symbol": ("line", "symbol", "spans", "class_names"),
    }
    for name, params in expected.items():
        function = getattr(anchors, name)
        parameters = list(inspect.signature(function).parameters)
        assert parameters == params, (
            f"{name}: parameters moved from {params} to {parameters} — "
            "the relocation must not redesign a signature (plan trap 7)"
        )


def test_the_signatures_are_unchanged() -> None:
    """T014, static half. Signature parameters compared by name and order."""
    _check_signatures_unchanged()


# --- US2-S2 / trap 5: the four `checked` appends are separate exits -----------


def _run_anchor_resolution(
    spec_dir: Path, spec_text: str, target_repo: str
) -> tuple[list, list, list]:
    """Drive `_check_anchor_resolution` over one trio and return its channels."""
    from factory.spec import anchors

    findings: list = []
    skipped: list = []
    checked: list = []
    anchors._check_anchor_resolution(
        spec_dir, spec_text, target_repo, findings, skipped, checked
    )
    return findings, skipped, checked


def _write_trio(spec_dir: Path, spec_body: str = "# Spec\n\n`factory/x.py:3`\n", plan: str = "# Plan\n", tasks: str = "# Tasks\n") -> None:
    """A minimal trio in its own parent (the frontmatter layer's specs root)."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        "---\nstate: draft\n---\n" + spec_body, encoding="utf-8"
    )
    (spec_dir / "plan.md").write_text(plan, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks, encoding="utf-8")


class TestAnchorResolutionCheckedAppends:
    """T014, trap 5. One append per exit, four exits, none merged."""

    def test_exit_1_no_documents(self, tmp_path: Path) -> None:
        """`spec.md` body empty, no `plan.md`, no `tasks.md` → checked, no findings."""
        spec_dir = tmp_path / "001-trio"
        spec_dir.mkdir(parents=True)
        # spec.md with empty body; the other two documents are absent.
        (spec_dir / "spec.md").write_text(
            "---\nstate: draft\n---\n", encoding="utf-8"
        )
        findings, skipped, checked = _run_anchor_resolution(
            spec_dir, "---\nstate: draft\n---\n", str(tmp_path)
        )
        assert checked == ["anchor_resolution"]
        assert findings == []
        assert skipped == []

    def test_exit_2_no_citations_found(self, tmp_path: Path) -> None:
        """Documents read but no citation at all → checked, no findings."""
        spec_dir = tmp_path / "002-trio"
        _write_trio(
            spec_dir,
            spec_body="# Spec\n\nNo citations in this prose.\n",
            plan="# Plan\n\nPlain prose.\n",
            tasks="# Tasks\n\nNothing cited.\n",
        )
        spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
        findings, skipped, checked = _run_anchor_resolution(
            spec_dir, spec_text, str(tmp_path)
        )
        assert checked == ["anchor_resolution"]
        assert findings == []
        assert skipped == []

    def test_exit_3_citations_but_no_paths_cited(self, tmp_path: Path) -> None:
        """Only unanchorable bare refs → checked after they are reported."""
        spec_dir = tmp_path / "003-trio"
        _write_trio(spec_dir, spec_body="# Spec\n\nA bare `:42` with no path.\n")
        spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
        findings, skipped, checked = _run_anchor_resolution(
            spec_dir, spec_text, str(tmp_path)
        )
        assert checked == ["anchor_resolution"]
        assert any("unanchorable" in finding.message for finding in findings)
        assert skipped == []

    def test_exit_4_the_normal_end(self, tmp_path: Path) -> None:
        """Citations that resolve against a real tree → checked at the end."""
        spec_dir = tmp_path / "004-trio"
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "x.py").write_text("line one\nline two\nline three\n", encoding="utf-8")
        _write_trio(spec_dir, spec_body="# Spec\n\n`x.py:2`\n")
        spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
        findings, skipped, checked = _run_anchor_resolution(
            spec_dir, spec_text, str(repo)
        )
        assert checked == ["anchor_resolution"]
        assert findings == []
        assert skipped == []

    def test_exit_4_reports_stale_anchors_before_appending(self, tmp_path: Path) -> None:
        """The same exit, carrying findings: appends happen before the exit."""
        spec_dir = tmp_path / "005-trio"
        repo = tmp_path / "repo2"
        repo.mkdir()
        (repo / "y.py").write_text("one\n", encoding="utf-8")
        _write_trio(spec_dir, spec_body="# Spec\n\n`y.py:99`\n")
        spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
        findings, skipped, checked = _run_anchor_resolution(
            spec_dir, spec_text, str(repo)
        )
        assert checked == ["anchor_resolution"]
        assert any("past end of file" in finding.message for finding in findings)