"""133-US4: the corpus parity test — both faces over every spec, agreeing.

US3 composed `validate_spec` and US9 made the verb a renderer over it; US4 is
the standing proof that the two faces cannot drift apart again — PR-8's "the
cheapest way to guarantee the two never disagree", and it is nearly free: the
corpus is on disk. Every spec directory in this repository's `specs/`, driven
through the library form and the CLI verb in one process, compared on the
verdict and on every channel.

- **T043 (US4-S1)** the verdict: the verb's exit code beside the library
  report's, for every spec.
- **T044 (US4-S2)** the per-layer findings with severities and messages — and,
  beside them, the three quieter channels (`checked`, `skipped`,
  `information`, `judge_evidence`), because agreement on the verdict alone
  would let a severity or a skip reason drift silently, which is the exact
  failure this story exists to prevent.
- **T045 (US4-S3, trap 12)** the corpus is enumerated by globbing at call
  time, proven by minting a spec into a scratch root and finding it, and by a
  source check that the parity test names no spec directory literally — so the
  guarantee covers the spec minted next week, not only the ones on disk today.
- **T046 (US4-S4, trap 15)** the CLI face is driven in-process through
  `factory.cli.main.main` with stdout captured — proven at call time by spies
  that refuse a spawn, and by a source check on the drive helper. One
  subprocess per spec over a corpus this size is minutes of suite wall time,
  and this repository already carries three tests that account for over half
  of it.
- **The control** the comparator, fed a corrupted report beside the verb's
  honest document, must disagree — loudly and by channel. A parity assertion
  that cannot fail is trap 23's vacuous control wearing this story's name:
  since US9 both faces share one composition, so the corpus run agrees on a
  healthy tree by construction, and only the comparator's willingness to name
  a difference makes the guarantee real.

Red first. The corpus itself agrees on the landed tree — that is the state
this story commits — so the red this story owes is the guards' and the
comparator's, each demonstrated against the wrong implementation it exists to
guard against. Since US9 the two faces share one composition, so the
sabotages are the seams a future story could drift: the library face patched
to flip every refusal (`factory.spec.validate_spec`), the comparator patched
to always agree, the corpus enumeration patched to a fixed list, the CLI
drive patched to shell out. All four went red through the real test
functions; the verbatim transcripts are pasted in
`tests/_133_us4_outputs/t048_corpus_parity_summary.txt` beside the green
run's summary line and wall clock (T048)::
"""


from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: US3's findings-store pin, reused rather than rebuilt. The `fixes` layer
#: resolves its store through `ERGANE_ROOT` and falls back to a cwd-relative
#: legacy root, so one pin is not isolation; `monkeypatch_env` pins both
#: candidates at the test's own tree, which makes the corpus run's `fixes`
#: answer — a deterministic skip, both faces alike — a fact about the run and
#: never about the machine (constitution II).
from tests.test_133_us3_validate_spec_composition import (
    monkeypatch_env,
    report_verdict_exit,
)


# --- the two faces and the comparison between them ----------------------------


def _corpus_spec_dirs(specs_root: Path | None = None) -> list[Path]:
    """Every spec directory under the corpus root, globbed at call time (T045).

    No literal list: the corpus is minted weekly, and a test that names spec
    directories stops covering new specs the moment one appears (US4-S3,
    trap 12). A directory is a spec when it carries `spec.md` — the filter the
    corpus controls in 089 and 102 already apply — so a scratch directory
    beside the corpus never enters the comparison.
    """
    root = REPO_ROOT / "specs" if specs_root is None else Path(specs_root)
    return sorted(
        entry
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "spec.md").is_file()
    )


def _drive_library(spec_dir: Path) -> Any:
    """The library face: `validate_spec`, one call, the typed report back (FR-003)."""
    from factory.spec import validate_spec

    return validate_spec(
        spec_dir, target_repo=str(REPO_ROOT), specs_root=str(REPO_ROOT / "specs")
    )


def _drive_verb(spec_dir: Path) -> tuple[int, dict[str, Any]]:
    """The CLI face: the entry point, in process, stdout captured (T046, FR-009).

    Through `factory.cli.main.main` — the same face an operator drives — with
    both streams swapped for captured buffers: one subprocess per spec over a
    corpus this size is minutes of wall time (trap 15). `--json` is the face
    that carries the per-layer findings and severities the comparison reads
    (US4-S2).
    """
    from factory.cli.main import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = main(
                [
                    "spec",
                    "validate",
                    "--json",
                    "--target-repo",
                    str(REPO_ROOT),
                    "--specs-root",
                    str(REPO_ROOT / "specs"),
                    str(spec_dir),
                ]
            )
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    return code, json.loads(stdout.getvalue())


def _comparisons(report: Any, code: int, document: dict[str, Any]) -> list[str]:
    """Every disagreement between the two faces, named by channel.

    The verdict first (US4-S1), then the per-layer findings with severities and
    messages (US4-S2) — and beside them the three quieter channels, because a
    renderer that folds one of them can still print an agreeing verdict:
    `checked`'s sequence is the seeded-then-appended order the goldens freeze
    (trap 3), `skipped` carries the reason strings a chain of not-checked
    layers is read from (trap 10), `information` the stated-not-counted notes,
    and `judge_evidence` is absent rather than null when the layer did not run
    (trap 21).
    """
    diffs: list[str] = []
    expected_code = report_verdict_exit(report)
    if code != expected_code:
        diffs.append(
            f"verdict: the verb exited {code}, the library report's verdict is "
            f"{report.verdict!r} (exit {expected_code})"
        )
    expected_findings = [
        {"layer": f.layer, "message": f.message, "severity": f.severity}
        for f in report.findings
    ]
    if document["findings"] != expected_findings:
        diffs.append(
            f"findings: the verb printed {document['findings']!r}, the library "
            f"returned {expected_findings!r}"
        )
    if document["checked"] != report.checked:
        diffs.append(
            f"checked: the verb printed {document['checked']!r}, the library "
            f"returned {report.checked!r}"
        )
    if [(e["layer"], e["reason"]) for e in document["skipped"]] != [
        (e["layer"], e["reason"]) for e in report.skipped
    ]:
        diffs.append(
            f"skipped: the verb printed {document['skipped']!r}, the library "
            f"returned {report.skipped!r}"
        )
    if [(n["layer"], n["message"]) for n in document["information"]] != [
        (n.layer, n.message) for n in report.information
    ]:
        diffs.append(
            f"information: the verb printed {document['information']!r}, the "
            f"library returned {[(n.layer, n.message) for n in report.information]!r}"
        )
    if report.judge_evidence is None:
        if "judge_evidence" in document:
            diffs.append(
                "judge_evidence: the verb emitted a key for a report the "
                "library did not make"
            )
    elif document.get("judge_evidence") != report.judge_evidence.as_dict():
        diffs.append(
            "judge_evidence: the verb's document and the library's report differ"
        )
    return diffs


# --- T043, T044, T047 / US4-S1, US4-S2 / FR-009: the corpus parity ------------


def test_both_faces_agree_over_every_corpus_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T043, T044, T047. Every spec in `specs/`, both faces, one process.

    The free correctness check PR-8 named. The findings-store candidates are
    pinned at this test's own tree first: the corpus declares `fixes:` keys
    that name rows of whatever ledger the host happens to carry, and a
    comparison that read it would be a function of the machine it runs on
    (constitution II). Pinned, the `fixes` layer skips identically on both
    faces on every host, and the agreement is about the faces, not the ledger.
    """
    root = tmp_path / "ergane-root"
    root.mkdir()
    monkeypatch_env(monkeypatch, root, tmp_path)

    spec_dirs = _corpus_spec_dirs()
    assert len(spec_dirs) > 100, (
        f"only {len(spec_dirs)} spec directories enumerated; the corpus is larger"
    )
    # The count T048's artifact pastes: visible under `-s`, captured otherwise.
    print(f"specs compared: {len(spec_dirs)}")

    for spec_dir in spec_dirs:
        report = _drive_library(spec_dir)
        code, document = _drive_verb(spec_dir)
        diffs = _comparisons(report, code, document)
        assert not diffs, f"{spec_dir.name}: " + "; ".join(diffs)


# --- the control: a comparator that cannot fail is not a control --------------


def test_the_comparator_refuses_a_corrupted_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. Fed a corrupted report beside the verb's honest document,
    the comparator names the drift — by channel, verdict included.

    Since US9 the two faces share one composition, so the corpus run agrees on
    a healthy tree by construction. What makes the guarantee real is that the
    comparison can fail: a severity flipped (US4-S2's named failure) and a
    finding invented (US4-S1's) are both flagged on one spec, not the corpus.
    """
    root = tmp_path / "ergane-root"
    root.mkdir()
    monkeypatch_env(monkeypatch, root, tmp_path)

    spec_dir = _corpus_spec_dirs()[0]
    report = _drive_library(spec_dir)
    code, document = _drive_verb(spec_dir)
    assert _comparisons(report, code, document) == [], (
        f"{spec_dir.name}: the corpus already disagrees; the corruption below "
        "would prove nothing"
    )

    from factory.spec import SpecFinding

    if report.findings:
        # Severity drift, kept verdict-consistent so the verdict flips too:
        # whatever the spec's honest verdict is, this corruption moves the
        # library report to the other side of it.
        first = report.findings[0]
        flipped = dataclasses.replace(
            first,
            severity="advisory" if first.severity == "refusal" else "refusal",
        )
        report.findings[0] = flipped
        if first.severity == "refusal":
            report.refusals.remove(first)
        else:
            report.refusals.append(flipped)
    else:
        invented = SpecFinding("parity-control", "invented for the control")
        report.findings.append(invented)
        report.refusals.append(invented)

    diffs = _comparisons(report, code, document)
    assert diffs, "the comparator accepted a corrupted report"
    assert any(d.startswith("findings:") for d in diffs), diffs
    assert any(d.startswith("verdict:") for d in diffs), diffs


# --- T045 / US4-S3 / trap 12: globbed at call time, never a literal list ------


def test_the_corpus_is_enumerated_by_globbing_at_call_time(tmp_path: Path) -> None:
    """T045, US4-S3. The corpus is enumerated, not listed.

    A test that names spec directories passes today and stops covering new
    specs the moment one is minted, which happens weekly here. Two halves: the
    enumeration proven at call time by minting a spec the corpus does not have
    yet and finding it, and the parity test proven to enumerate through the
    helper with no spec directory named literally in its source.
    """
    minted = tmp_path / "999-minted-after-this-story"
    minted.mkdir()
    (minted / "spec.md").write_text("# minted later\n", encoding="utf-8")

    assert minted in _corpus_spec_dirs(tmp_path), (
        "a spec minted after this story landed was not enumerated; the corpus "
        "list has stopped being a glob"
    )

    parity_source = inspect.getsource(test_both_faces_agree_over_every_corpus_spec)
    assert "_corpus_spec_dirs(" in parity_source, (
        "the parity test no longer enumerates through the globbing helper"
    )
    for spec_dir in _corpus_spec_dirs():
        for quoting in ('"{}"', "'{}'"):
            assert quoting.format(spec_dir.name) not in parity_source, (
                f"{spec_dir.name} is named literally in the parity test; the "
                "enumeration must glob at call time"
            )


# --- T046 / US4-S4 / trap 15: in process, no subprocess per spec --------------


def test_the_cli_face_is_driven_in_process(tmp_path: Path) -> None:
    """T046, US4-S4. The entry point, in process, stdout captured — no spawn.

    Two halves: the drive run under spies that refuse a `subprocess` spawn,
    over a real corpus spec, and the drive helper's source — through
    `factory.cli.main.main` with the streams captured, naming no subprocess.
    More than a hundred spec directories at one process each is minutes of
    suite wall time this repository does not have.
    """
    spawned: list[str] = []

    def _refuse(name: str) -> Callable[..., Any]:
        def _spy(*args: Any, **kwargs: Any) -> Any:
            spawned.append(name)
            raise AssertionError(f"subprocess.{name} spawned during the CLI drive")
        return _spy

    saved_run, saved_popen = subprocess.run, subprocess.Popen
    subprocess.run = _refuse("run")
    subprocess.Popen = _refuse("Popen")
    try:
        _code, _document = _drive_verb(_corpus_spec_dirs()[0])
    finally:
        subprocess.run, subprocess.Popen = saved_run, saved_popen
    assert spawned == [], (
        f"the CLI drive spawned a subprocess: {spawned}; trap 15 forbids it"
    )

    source = inspect.getsource(_drive_verb)
    for spawn in ("subprocess.run", "subprocess.Popen", "subprocess.call", "Popen("):
        assert spawn not in source, (
            f"the CLI drive names {spawn}; it must run in process (trap 15)"
        )
    assert "redirect_stdout" in source, "the CLI drive must capture stdout"
    assert "factory.cli.main" in source, (
        "the CLI face must be driven through the CLI entry point"
    )