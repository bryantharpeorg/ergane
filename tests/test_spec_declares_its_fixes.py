"""073-US1: a spec declares which findings it fixes, in its own frontmatter.

The fix relation between a spec and a finding is a *declared* fact or it is a
guess about prose. Measured on this repository's ledger, the guess is wrong:
`interpreter/ci-failure-never-reaches-an-agent` is named by six specs — two as
their fix, one in an out-of-scope list, one as background, and one in a note
saying the finding is *regressed*. Any rule that reads prose reads four of those
as a fix and one of the four says the opposite. So the relation gets a key.

The key is `fixes:`, a list of finding keys, and this file holds the whole of
what US1 adds:

- **It is additive (FR-001).** 68 specs in the corpus omit it, and every one of
  them must keep parsing exactly as it did — the record reads `[]` and the spec
  is valid. `depends_on_landed` set that precedent and `fixes` copies it.
- **A scalar where a list belongs is refused, naming the spec (FR-002).** This
  repository has already paid once for a frontmatter scalar that a reader was
  happy to iterate character by character. The shape check is the same idiom
  `depends_on_landed` uses, deliberately — a second idiom in the same function
  is a defect waiting for a reader who assumes they match.
- **The grammar stays closed (FR-003).** The frontmatter rides
  `PromptSources.spec_text` whole into agent payloads, which is why the key set
  is closed and why widening it is a visible act: this story widens it by
  exactly one name, and a key that is none of the three is still refused.

Every corpus here is supplied under `tmp_path` — never this repository's own
`specs/`, whose states flip weekly and whose findings are the running factory's
production evidence. The same goes for the findings store the `fixes` layer
reads: see `_own_findings_store` below, which takes two pins because store
resolution has two candidates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

import factory.doctor.cli as _doctor_cli
from factory.cli.main import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, report
from factory.roadmap.models import RoadmapError, SpecState, read_roadmap

#: Two real finding keys from this repository's ledger, spelled as the store
#: spells them (`<category>/<slug>`), so the fixture exercises the shape the
#: sweep will actually meet rather than a placeholder.
FINDING_KEYS = [
    "interpreter/ci-failure-never-reaches-an-agent",
    "ci/test-suite-pins-the-operator-dial",
]


# --- the store, supplied too --------------------------------------------------


@pytest.fixture(autouse=True)
def _own_findings_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Put both findings-store candidates under this test's own `tmp_path`.

    `ERGANE_ROOT` names the first candidate and is not enough on its own: when
    the resolved runtime root holds no ledger, `_resolve_store_path` falls back
    to the legacy runtime root *relative to the working directory*, which on an
    operator's host is the operator's real ledger. So the test below read
    whatever findings the machine happened to hold — green on a fresh clone, red
    on the machine that does the building, with `assert 'fixes' in []` (123-US2,
    trap 4).

    The legacy pin names a directory that is never created, because what that
    candidate is wanted for is absence. A test wanting a store puts one at
    `<runtime root>/doctor.db`, which wins outright.
    """
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(
        _doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-runtime-root"
    )


def _seed_store(tmp_path: Path, *keys: str) -> Path:
    """A findings ledger under `tmp_path`, holding exactly `keys`.

    Seeded with the keys the fixture spec declares, so the `fixes` layer has
    something true to verify against and reports the layer *checked* — the
    outcome an operator's populated host used to reach by accident.
    """
    store_path = tmp_path / "doctor.db"
    conn = connect(store_path)
    try:
        for key in keys:
            category, _, _slug = key.partition("/")
            report(
                conn,
                Finding(
                    key=key,
                    category=category,
                    severity=Severity.INFO,
                    status=Status.OPEN,
                    summary=f"supplied row for {key}",
                    refs=["factory/foo.py:1"],
                    notes=None,
                    source="test",
                    occurrences=1,
                    first_seen="2026-08-30T00:00:00Z",
                    last_seen="2026-08-30T00:00:00Z",
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at="2026-08-30T00:00:00Z",
            )
    finally:
        conn.close()
    return store_path


# --- supplied corpora ---------------------------------------------------------


def _write_spec(specs_root: Path, spec_dir: str, frontmatter: str, body: str = "") -> Path:
    """One spec under a supplied corpus: frontmatter, then prose.

    `frontmatter` is the YAML between the fences, without them. The body
    defaults to a heading, because the roadmap reader consults nothing below the
    fence and a spec with no prose is still a spec to it.
    """
    directory = specs_root / spec_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "spec.md"
    text = f"---\n{frontmatter}\n---\n\n# Feature Specification: {spec_dir}\n{body}"
    path.write_text(text, encoding="utf-8")
    return path


def _read(specs_root: Path) -> dict[str, Any]:
    return {entry.spec_dir: entry for entry in read_roadmap(specs_root).entries}


def _findings(specs_root: Path) -> list[Any]:
    with pytest.raises(RoadmapError) as caught:
        read_roadmap(specs_root)
    return list(caught.value.findings)


# --- T001 (US1-S1): the key is exposed on the record --------------------------


def test_a_spec_that_declares_fixes_exposes_them_on_the_record(tmp_path: Path) -> None:
    """FR-001: `fixes:` carries a list of finding keys onto the parsed record.

    This is the fact every other story in the epic rests on. Without it the
    sweep can produce candidates and nothing else, because prose is not a
    declaration — so the assertion is on the record, in order, not on a count.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "001-declares",
        "state: ready\n"
        f"fixes:\n  - {FINDING_KEYS[0]}\n  - {FINDING_KEYS[1]}\n",
    )

    entry = _read(specs_root)["001-declares"]

    assert entry.fixes == FINDING_KEYS
    assert entry.state is SpecState.READY


def test_fixes_travels_beside_depends_on_landed_without_disturbing_it(
    tmp_path: Path,
) -> None:
    """The new key is orthogonal: a spec may carry both, and each reads its own.

    `fixes` is a list of *finding* keys and `depends_on_landed` a list of *spec*
    directories; they are two lists of strings on the same block, and the reader
    must not confuse one for the other.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-alpha", "state: landed\n")
    _write_spec(
        specs_root,
        "002-both",
        "state: ready\n"
        "depends_on_landed: [001-alpha]\n"
        f"fixes: [{FINDING_KEYS[0]}]\n",
    )

    entry = _read(specs_root)["002-both"]

    assert entry.depends_on_landed == ["001-alpha"]
    assert entry.fixes == [FINDING_KEYS[0]]


# --- T002 (US1-S2): the key is additive ---------------------------------------


def test_a_spec_that_omits_fixes_reads_an_empty_list_and_is_valid(
    tmp_path: Path,
) -> None:
    """FR-001: absent reads `[]`, and the spec is valid.

    68 specs in the corpus omit the key. Every one of them must keep parsing
    exactly as it did — the same additive discipline that let the frontmatter
    grammar be adopted at all (a spec with no frontmatter reads `draft`).
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-silent", "state: ready\n")

    entry = _read(specs_root)["001-silent"]

    assert entry.fixes == []
    assert entry.state is SpecState.READY


def test_a_spec_with_no_frontmatter_at_all_still_reads_an_empty_fixes(
    tmp_path: Path,
) -> None:
    """The no-frontmatter path constructs its own entry, and must default too.

    `read_roadmap` builds a `SpecEntry` directly for a spec with no fence pair,
    bypassing the shaping function entirely. A default that lives only in the
    shaper would leave this path carrying whatever the dataclass says — which is
    exactly why the field's default is a `default_factory` and not a bare `[]`.
    """
    specs_root = tmp_path / "specs"
    directory = specs_root / "001-bare"
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(
        "# Feature Specification: bare\n\nNo frontmatter at all.\n", encoding="utf-8"
    )

    entry = _read(specs_root)["001-bare"]

    assert entry.state is SpecState.DRAFT
    assert entry.fixes == []


def test_an_explicit_null_fixes_reads_an_empty_list(tmp_path: Path) -> None:
    """`fixes:` with nothing after it is YAML `None`, and reads `[]`.

    An author who wrote the key and then deleted its one entry has declared
    nothing, not an error — the same reading `depends_on_landed` gives, copied
    rather than re-decided.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-empty", "state: draft\nfixes:\n")

    assert _read(specs_root)["001-empty"].fixes == []


def test_each_record_carries_its_own_list(tmp_path: Path) -> None:
    """Two specs, two lists — never one list shared between records.

    A bare `= []` default on a frozen dataclass is a single list shared by every
    entry that takes the default; the type checker does not catch it and the
    corpus reads correctly right up until something appends. Mutating one
    record's list must leave the other's alone.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-one", "state: draft\n")
    _write_spec(specs_root, "002-two", "state: draft\n")

    entries = _read(specs_root)
    entries["001-one"].fixes.append("sentinel/leaked")

    assert entries["002-two"].fixes == []


# --- T003 (US1-S3): a scalar where a list belongs is refused ------------------


def test_a_bare_string_fixes_is_refused_naming_the_spec(tmp_path: Path) -> None:
    """FR-002: a scalar `fixes:` is refused, and the finding names the offender.

    A scalar where a list belongs is the frontmatter defect this repository has
    already paid for once: read as a list it is a list of characters, and every
    consumer downstream believes the spec declared 44 fixes. The refusal names
    the spec directory *and* quotes the value back, because the audience is an
    author who has to go edit one line of one file.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-scalar", f"state: ready\nfixes: {FINDING_KEYS[0]}\n")

    (fault,) = _findings(specs_root)

    rendered = str(fault)
    assert "001-scalar" in rendered
    assert "fixes" in rendered
    assert FINDING_KEYS[0] in rendered


def test_a_list_carrying_a_non_string_is_refused(tmp_path: Path) -> None:
    """A list of the wrong element type is refused too — a key is a string.

    `fixes: [- 12]` is not a finding key under any reading, and admitting it
    would push the type error downstream into the sweep, where the offending
    spec is no longer in hand to name.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-nested", "state: ready\nfixes:\n  - 12\n")

    (fault,) = _findings(specs_root)

    assert "001-nested" in str(fault)
    assert "fixes" in str(fault)


def test_a_rejected_fixes_yields_no_partial_roadmap(tmp_path: Path) -> None:
    """One malformed spec refuses the corpus — no well-formed remainder is emitted.

    Emitting the sound specs of a broken corpus is the worst outcome available:
    a roadmap that looks usable while the one broken spec is silent. `fixes`
    joins that discipline rather than getting an exception from it.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-sound", "state: ready\n")
    _write_spec(specs_root, "002-scalar", "state: ready\nfixes: a-bare-string\n")

    with pytest.raises(RoadmapError):
        read_roadmap(specs_root)


# --- T004 (US1-S4): the control — the grammar is still closed -----------------


def test_an_unknown_key_is_still_refused(tmp_path: Path) -> None:
    """FR-003: the grammar widens by exactly one name, and stays closed.

    **The control.** A story that adds a key to a closed set can pass every
    positive assertion above by opening the set entirely, and the corpus would
    then accept anything an author typed — including the misspelling of `fixes`
    that this test is really about. The frontmatter rides
    `PromptSources.spec_text` whole into agent payloads; a closed key set is
    what keeps that text provably inert.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-x", "state: ready\npriority: P1\n")

    (fault,) = _findings(specs_root)

    assert fault.rule == "unknown_key"
    assert "priority" in str(fault)
    assert "001-x" in str(fault)


def test_a_misspelled_fixes_is_refused_and_the_grammar_names_all_three(
    tmp_path: Path,
) -> None:
    """The refusal quotes the grammar back, and the grammar is now three names.

    `fixes` is the one name added. An author who wrote `fixed:` gets told what
    the vocabulary is, and the vocabulary must name the key they meant — a
    rejection that lists the grammar without the new key sends them to the wrong
    fix.
    """
    specs_root = tmp_path / "specs"
    _write_spec(specs_root, "001-typo", "state: ready\nfixed: [a/b]\n")

    (fault,) = _findings(specs_root)

    rendered = str(fault)
    assert fault.rule == "unknown_key"
    assert "fixed" in rendered
    for name in ("state", "depends_on_landed", "fixes"):
        assert f"'{name}'" in rendered


# --- T005 (US1-S5): `ergane spec validate` is unchanged -----------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


_STORY_BODY = """
## Requirements *(mandatory)*

- **FR-001**: The system MUST do the thing.

### User Story 1 - The thing happens (Priority: P1)

As the operator, I want the thing.

**Acceptance Scenarios**:

1. **Given** a thing, **When** I act, **Then** it works.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
"""

_TRIO_TASKS = (
    "# Tasks\n\n"
    "## Phase 1: User Story 1 - The thing happens\n\n"
    "- [ ] T001 [US1-S1] prove the thing happens\n"
)


def _sound_trio(specs_root: Path, spec_dir: str, frontmatter: str) -> Path:
    """A spec whose whole trio validates: `ergane spec validate` exits zero on it.

    Six layers run inside `validate`, and only the first reads frontmatter. The
    other five need a plan and a task slice whose phase heading names the story,
    or the run reports refusals that have nothing to do with this story and the
    comparison below would be between two piles of unrelated noise.
    """
    path = _write_spec(specs_root, spec_dir, frontmatter, body=_STORY_BODY)
    (path.parent / "plan.md").write_text(
        "# Plan\n\nOne reader, one key.\n", encoding="utf-8"
    )
    (path.parent / "tasks.md").write_text(_TRIO_TASKS, encoding="utf-8")
    return path.parent


def test_validate_reports_the_same_result_with_and_without_fixes(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """US1-S5 / US3-S4: a spec omitting `fixes:` is unchanged; one declaring it
    now has the fixes layer reported.

    089-US3 added a ledger check for declared `fixes:` keys, so the two specs no
    longer produce identical reports. The control that still matters is the
    spec without the key: it must take no new code path and get the same
    layers and verdict it did before US3.

    The ledger is supplied, not found (123-US2, FR-004). Reading whatever store
    the host happens to carry is what made this test's verdict a fact about the
    machine: the operator's own ledger holds the key the declaring spec names,
    so the layer *ran* there and the skip this test used to assert was empty.
    A store built here decides both directions the same way.
    """
    store_path = _seed_store(tmp_path, FINDING_KEYS[0])

    specs_root = tmp_path / "specs"
    _sound_trio(
        specs_root,
        "001-declares",
        f"state: draft\nfixes:\n  - {FINDING_KEYS[0]}\n",
    )
    _sound_trio(specs_root, "002-omits", "state: draft\n")

    declaring = run("spec", "validate", "--json", str(specs_root / "001-declares"))
    omitting = run("spec", "validate", "--json", str(specs_root / "002-omits"))

    assert declaring.code == 0
    assert omitting.code == 0
    assert declaring.json["findings"] == []
    assert omitting.json["findings"] == []

    # The spec that omits `fixes:` must show no trace of the new layer.
    assert "fixes" not in omitting.json["checked"]
    assert "fixes" not in [entry["layer"] for entry in omitting.json["skipped"]]

    # The spec that declares `fixes:` has the layer reported, and against the
    # ledger supplied above: it ran rather than skipping, and neither outcome
    # was decided by a store this test did not build.
    assert "fixes" in declaring.json["checked"]
    assert "fixes" not in [entry["layer"] for entry in declaring.json["skipped"]]

    # US2-S3: the store it resolved is under this test's own temporary
    # directory. The layer names the path it read, which is what makes that
    # assertable rather than merely intended.
    verified = [note for note in declaring.json["information"] if note["layer"] == "fixes"]
    assert len(verified) == 1
    assert str(store_path) in verified[0]["message"]
    assert str(tmp_path) in verified[0]["message"]


def test_validate_refuses_a_scalar_fixes_naming_the_frontmatter_layer(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """The refusal reaches the operator through validate, not only through the reader.

    `validate` is where an author meets the grammar — it is the command run
    before a spec is dispatched. A shape rule the reader enforces and validate
    swallows is a rule nobody is held to at the moment it would help.
    """
    specs_root = tmp_path / "specs"
    _sound_trio(specs_root, "001-scalar", "state: draft\nfixes: a-bare-string\n")

    result = run("spec", "validate", str(specs_root / "001-scalar"))

    assert result.code == 1
    output = result.stdout + result.stderr
    assert "frontmatter" in output
    assert "fixes" in output
    assert "001-scalar" in output
