"""What the roadmap's spec frontmatter parses into, and what it refuses.

US1's grammar is the deriver's discipline applied one level up: every spec
declares its intent — `draft`, `ready`, `deferred`, or attested `landed` — in a
frontmatter block, and one reader turns a `specs/` corpus into a roadmap graph
of states and `depends_on_landed` edges. The grammar is *closed*: unknown keys
and unknown states are rejected naming the offender and the file, because
silently dropping a key an author wrote is how a roadmap comes to mean something
other than it says (FR-001).

Three properties carry the weight here:

- **The field is additive (FR-002).** A spec with no frontmatter reads `draft`,
  so every existing spec stays valid unchanged. Adopting the grammar must not
  invalidate or alter the meaning of any spec already on disk.
- **Rejection names the offender and the file.** The audience is an author who
  has to go edit one line of one spec, so every finding names the offending key
  (or state) *and* the file it came from — the same discipline as the deriver's
  `unknown_key` rule, one level up.
- **The reader is pure.** It opens no file beyond the corpus it is handed, the
  `test_derivation_opens_no_file` pattern: a function that could read
  `personas.yaml` or the registry would smuggle facts the frontmatter does not
  declare.

The corpus lives under `tests/fixtures/roadmap/<case>/specs/<spec-dir>/spec.md`,
mirroring the real `specs/` root. Every rejection fixture is a corpus the
reader rejects; the `valid` fixture exercises every state plus a real, blocked
edge and a no-frontmatter spec.

Written before `factory/roadmap/models.py` exists (T003 precedes T006): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from factory.roadmap.models import (
    RoadmapError,
    SpecEntry,
    SpecState,
    read_roadmap,
)

CORPUS = Path(__file__).resolve().parent / "fixtures" / "roadmap"


def corpus(case: str) -> Path:
    """The specs-root for one fixture case (a directory holding `specs/`)."""
    return CORPUS / case / "specs"


def read(case: str) -> Any:
    return read_roadmap(corpus(case))


def findings(case: str) -> list[Any]:
    with pytest.raises(RoadmapError) as caught:
        read(case)
    return list(caught.value.findings)


# Acceptance (FR-001, FR-002) -------------------------------------------------


def test_the_valid_corpus_yields_every_state_and_edge() -> None:
    """Every state the grammar admits, plus one attested-landed edge, parsed.

    `001-alpha` attests `landed`; `002-bravo` has no frontmatter and reads
    `draft` (FR-002); `003-ready` is `ready` and depends on the attested
    `001-alpha`; `004-blocked` is `ready` and depends on the draft `002-bravo`;
    `006-deferred` is `deferred`. The corpus is the whole accepting case.
    """
    roadmap = read("valid")

    entries = {entry.spec_dir: entry for entry in roadmap.entries}
    assert entries["001-alpha"].state is SpecState.LANDED
    assert entries["002-bravo"].state is SpecState.DRAFT
    assert entries["003-ready"].state is SpecState.READY
    assert entries["003-ready"].depends_on_landed == ["001-alpha"]
    assert entries["004-blocked"].state is SpecState.READY
    assert entries["004-blocked"].depends_on_landed == ["002-bravo"]
    assert entries["006-deferred"].state is SpecState.DEFERRED


def test_a_spec_without_frontmatter_reads_draft() -> None:
    """FR-002: the field is additive — no frontmatter means `draft`.

    `002-bravo` carries no frontmatter block at all; it must parse as `draft`,
    never as an error, so adopting the grammar never invalidates an existing
    spec (acceptance scenario 2).
    """
    roadmap = read("valid")
    bravo = next(e for e in roadmap.entries if e.spec_dir == "002-bravo")

    assert bravo.state is SpecState.DRAFT
    assert bravo.depends_on_landed == []


def test_a_landed_state_is_attested_only_in_frontmatter() -> None:
    """`state: landed` is the operator's attestation for pre-roadmap work.

    001/002/005 were never epics; nothing will ever observe them landing, so
    `landed` may be written by the operator as an attestation. At US1 the only
    path to `landed` is the frontmatter value — observed-landed arrives in US2.
    """
    roadmap = read("valid")
    alpha = next(e for e in roadmap.entries if e.spec_dir == "001-alpha")

    assert alpha.state is SpecState.LANDED


# Rejections (FR-001) ---------------------------------------------------------

#: One row per grammar rule the reader enforces, mirroring the deriver's
#: REJECTIONS table: (fixture, rule, the name that must appear in the finding,
#: the file's spec-dir). `rule` is the slug; `named` is the offender string.
GRAMMAR_REJECTIONS = [
    ("unknown_key", "unknown_key", "priority", "001-x"),
    ("unknown_state", "unknown_state", "building", "001-x"),
    ("non_mapping", "non_mapping", "mapping", "001-x"),
    ("dangling_dep", "dangling_dep", "002-nowhere", "001-x"),
]


@pytest.mark.parametrize(
    ("fixture", "rule", "named", "spec_dir"),
    GRAMMAR_REJECTIONS,
    ids=[row[0] for row in GRAMMAR_REJECTIONS],
)
def test_each_grammar_rejection_names_offender_and_file(
    fixture: str, rule: str, named: str, spec_dir: str
) -> None:
    """FR-001: unknown keys and unknown values reject naming the offender and file.

    Silently dropping a key an author wrote is how a roadmap comes to mean
    something other than it says. Each fixture carries exactly one defect, so
    exactly one finding is assertable, and it names both the offender (the bad
    key or value) and the file it came from (acceptance scenario 3).
    """
    faults = findings(fixture)

    assert len(faults) == 1
    fault = faults[0]
    assert fault.rule == rule
    assert named in str(fault)
    # The file is named — never a bare "rejected".
    assert spec_dir in str(fault)


def test_a_cycle_is_reported_naming_only_the_specs_on_it() -> None:
    """Acceptance scenario 4: a dependency cycle names only the cycle's members.

    `001-a` ⇄ `002-b` is the cycle; `003-c` is outside it and must not appear in
    the finding — the author's next move is to delete one of the cycle's edges,
    and naming every spec would leave them to re-derive the cycle by hand.
    """
    (fault,) = findings("cycle")

    assert fault.rule == "cycle"
    rendered = str(fault)
    assert "001-a" in rendered and "002-b" in rendered
    assert "003-c" not in rendered


def test_a_rejected_corpus_emits_no_entries() -> None:
    """A grammar failure yields no partial roadmap — nothing is emitted.

    Emitting the well-formed specs of a broken corpus would be the worst
    outcome: a roadmap that looks usable while the one broken spec is silent.
    """
    with pytest.raises(RoadmapError):
        read("unknown_key")


# Purity (the `test_derivation_opens_no_file` pattern) -------------------------


def test_the_reader_opens_no_file_beyond_the_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader is pure over the corpus — no registry, no `personas.yaml`.

    `read_roadmap` walks the corpus it is handed and reads each `spec.md`, and
    nothing else. Breaking every read path after the corpus is collected would
    still let it parse — but the point is it never reaches outside the corpus.
    The pattern mirrors `test_derivation_opens_no_file`: a function that could
    read other files would smuggle facts the frontmatter does not declare.
    """
    # The reader must be able to read the corpus; intercept everything else.
    real_open = Path.open
    real_read_text = Path.read_text

    def refuse_outside_corpus(path: Path, *args: object, **kwargs: object) -> Any:
        raise AssertionError(
            f"reader must not read outside the corpus: {path}"
        )

    def guarded_open(self: Path, *args: object, **kwargs: object) -> Any:
        # Allow reads under the corpus root; refuse everything else.
        try:
            self.resolve().relative_to(CORPUS.resolve())
        except ValueError:
            raise refuse_outside_corpus(self) from None
        return real_open(self, *args, **kwargs)

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> Any:
        try:
            self.resolve().relative_to(CORPUS.resolve())
        except ValueError:
            raise refuse_outside_corpus(self) from None
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    # Guard the builtin too, in case the reader uses it directly.
    monkeypatch.setattr(builtins, "open", lambda *a, **k: refuse_outside_corpus(Path(str(a[0])) if a else Path()))

    roadmap = read("valid")
    assert {e.spec_dir for e in roadmap.entries} == {
        "001-alpha",
        "002-bravo",
        "003-ready",
        "004-blocked",
        "006-deferred",
    }