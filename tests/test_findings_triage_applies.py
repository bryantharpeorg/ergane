"""US3: `ergane findings triage --apply` enacts only what was declared.

Every fixture here is *supplied* — a store built with `connect()` on a
`tmp_path`, and a specs corpus built as files under `tmp_path`, sometimes inside
a throwaway git repository (plan trap 13). Nothing in this file opens
`.factory/`, the running factory's `doctor.db`, or this repository's real
`specs/`.

US2 proved the classifier can tell the six classes apart. This file proves the
sweep *acts* on exactly two of them and on nothing else, which is a separate
claim: a classifier that is right and a writer that is generous still closes a
live regression.

The silences carry as much weight as the writes (plan trap 15). A `--apply` that
resolved every row it was offered would satisfy every positive assertion here
and none of these:

- `test_a_prose_candidate_is_untouched` — prose is not a declaration, and the
  candidate class is the one `--apply` may never act on (US3-S2, FR-015,
  trap 1).
- `test_a_seen_after_fix_finding_is_untouched` — status, occurrences,
  `last_seen` and the event trail all byte-for-byte (US3-S3, FR-015).
- `test_the_annotation_is_idempotent_and_costs_no_recurrence` — the annotation
  goes nowhere near `report()`, which would add a phantom occurrence to a ledger
  whose whole purpose is counting recurrence (US3-S6, FR-018, trap 5).
- `test_nothing_declared_means_no_status_changes` — the control (US3-S7).
- `test_only_the_resolvable_classes_are_ever_written_to` — FR-019 stated as the
  one predicate it is.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli import main as main_module
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import (
    ANNOTATION_MARKER,
    connect,
    list_events,
    report,
    resolve,
)
from factory.doctor.triage import (
    ANNOTATABLE_CLASSES,
    CLASS_ORDER,
    RESOLVABLE_CLASSES,
    UNTOUCHED_CLASSES,
)


# --- harness ------------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str]) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def apply_triage() -> Callable[..., Run]:
    """Run `ergane findings triage --apply` over a supplied store and corpus."""

    def _caller(db: Path, specs_root: Path, *extra: str) -> Run:
        run = _invoke(
            [
                "findings",
                "triage",
                "--apply",
                "--db",
                str(db),
                "--specs-root",
                str(specs_root),
                *extra,
            ]
        )
        assert run.code == 0, f"triage --apply failed: {run.stderr}"
        return run

    return _caller


class Row(NamedTuple):
    """Every field US3 asserts about, read straight out of the store."""

    status: str
    occurrences: int
    last_seen: str
    notes: str | None
    resolution: str | None
    resolved_at: str | None
    events: int

    @property
    def annotation(self) -> str | None:
        """The single triage annotation line in this row's notes, if any."""
        lines = [
            line
            for line in (self.notes or "").splitlines()
            if line.startswith(ANNOTATION_MARKER)
        ]
        assert len(lines) <= 1, f"annotation appears {len(lines)} times: {self.notes!r}"
        return lines[0] if lines else None


def _row(db: Path, key: str) -> Row:
    conn = connect(db)
    try:
        found = conn.execute(
            "SELECT status, occurrences, last_seen, notes, resolution, resolved_at "
            "FROM findings WHERE key = ?",
            (key,),
        ).fetchone()
        assert found is not None, f"no finding {key!r} in the store"
        return Row(*found, events=len(list_events(conn, key)))
    finally:
        conn.close()


def _statuses(db: Path) -> dict[str, str]:
    conn = connect(db)
    try:
        return dict(conn.execute("SELECT key, status FROM findings").fetchall())
    finally:
        conn.close()


def _resolved_keys(db: Path) -> set[str]:
    conn = connect(db)
    try:
        return {
            key
            for (key,) in conn.execute(
                "SELECT key FROM findings WHERE status = 'resolved'"
            ).fetchall()
        }
    finally:
        conn.close()


def _seed(
    conn: Any,
    key: str,
    *,
    seen_at: str,
    source: str = "probe",
    notes: str | None = None,
) -> None:
    """Report one finding once, so it lands `open` with `occurrences` 1."""
    report(
        conn,
        Finding(
            key=key,
            category=key.split("/")[0],
            severity=Severity.WARNING,
            status=Status.OPEN,
            summary=f"summary for {key}",
            refs=[],
            notes=notes,
            source=source,
            occurrences=1,
            first_seen=seen_at,
            last_seen=seen_at,
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        ),
        seen_at=seen_at,
    )


def _store(tmp_path: Path) -> Path:
    return tmp_path / "store" / "doctor.db"


def _ago(days: int) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- a supplied specs corpus, optionally under git ----------------------------


def _write_spec(
    specs_root: Path,
    spec_dir: str,
    *,
    state: str,
    fixes: list[str] | None = None,
    body: str = "Nothing to see here.\n",
) -> Path:
    directory = specs_root / spec_dir
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"state: {state}"]
    if fixes is not None:
        lines.append("fixes:")
        lines.extend(f"  - {key}" for key in fixes)
    lines.extend(["---", "", body])
    (directory / "spec.md").write_text("\n".join(lines), encoding="utf-8")
    return directory


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "Triage Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Triage Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }
    )
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _landing_corpus(tmp_path: Path, *, fixes: list[str]) -> Path:
    """A git repo whose spec was drafted, then attested landed, on 2026-08-10."""
    repo = tmp_path / "repo"
    specs_root = repo / "specs"
    specs_root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )

    _write_spec(specs_root, "012-plugs-the-leak", state="draft")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "draft", when="2026-08-01T00:00:00+00:00")

    _write_spec(specs_root, "012-plugs-the-leak", state="landed", fixes=fixes)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "attest landed", when="2026-08-10T00:00:00+00:00")

    return specs_root


# --- US3-S1 (T028): a declaration closes its row ------------------------------


def test_a_fixed_finding_is_resolved_naming_the_declaring_spec(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S1 / FR-014: resolved, and the resolution names the spec directory."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
    finally:
        conn.close()

    run = apply_triage(db, specs_root)
    assert "ops/leaks-a-key" in run.stdout
    assert "012-plugs-the-leak" in run.stdout

    row = _row(db, "ops/leaks-a-key")
    assert row.status == "resolved"
    assert row.resolution == "012-plugs-the-leak"
    assert row.resolved_at is not None


def test_the_apply_document_reports_what_it_resolved(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """FR-014: `--json` says the same thing the human report does."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
    finally:
        conn.close()

    document = apply_triage(db, specs_root, "--json").json
    assert document["applied"]["resolved"] == [
        {"key": "ops/leaks-a-key", "resolution": "012-plugs-the-leak"}
    ]
    assert document["applied"]["annotated"] == []
    assert document["applied"]["folds"] == []


# --- US3-S2 (T029): prose is never a declaration ------------------------------


def test_a_prose_candidate_is_untouched(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S2 / FR-015 / FR-019 / trap 1: naming is not fixing.

    On the corpus this spec was written against one key was named by six landed
    specs — two as their fix, one in an out-of-scope list, one as background, and
    one in a note saying the finding is *regressed*. A `--apply` that read prose
    as a declaration would have closed a live regression.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "020-fixes-it-maybe",
        state="landed",
        body="This epic was filed against `ops/leaks-a-key` and closes it.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at=_ago(1), notes="Filed by the probe.")
    finally:
        conn.close()

    before = _row(db, "ops/leaks-a-key")
    apply_triage(db, specs_root)
    after = _row(db, "ops/leaks-a-key")

    assert after == before
    assert after.status == "open"
    assert after.notes == "Filed by the probe."


# --- US3-S3 (T030): a later sighting is the top of the queue ------------------


def test_a_seen_after_fix_finding_is_untouched(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S3 / FR-015: status, occurrences, `last_seen` and the events, all held.

    This class is the top of the operator's queue: a spec declared the fix and
    the probe saw the defect anyway. Annotating it would be a write; closing it
    would be a lie. `--apply` does neither.
    """
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-12T09:00:00Z")
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-13T09:00:00Z")
    finally:
        conn.close()

    before = _row(db, "ops/leaks-a-key")
    assert before.occurrences == 2

    apply_triage(db, specs_root)

    after = _row(db, "ops/leaks-a-key")
    assert after == before
    assert after.status == "open"
    assert after.occurrences == 2
    assert after.last_seen == "2026-08-13T09:00:00Z"
    assert after.notes is None
    assert after.events == before.events


# --- US3-S4 (T031): the fold ---------------------------------------------------


def test_every_member_of_a_fragmented_class_is_folded(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S4 / FR-016: every member resolved, naming prefix and count.

    The surviving class key is the shared prefix — the key the detector will
    mint once it stops keying on the node — and the report names it so the
    operator can find the one row that replaces the pile.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    members = [
        "hardening/agent-worktree-boundary/070/us4",
        "hardening/agent-worktree-boundary/071/us1",
        "hardening/agent-worktree-boundary/072/us2",
    ]
    db = _store(tmp_path)
    conn = connect(db)
    try:
        for index, key in enumerate(members):
            _seed(conn, key, seen_at=_ago(index + 1), source="boundary-detector")
    finally:
        conn.close()

    run = apply_triage(db, specs_root)

    for key in members:
        row = _row(db, key)
        assert row.status == "resolved", key
        assert "hardening/agent-worktree-boundary" in (row.resolution or ""), key
        assert "3" in (row.resolution or ""), key

    # FR-016: the report names the surviving class key.
    assert "hardening/agent-worktree-boundary" in run.stdout

    document = apply_triage(db, specs_root, "--json").json
    # Second pass: already resolved, so out of the pool and folded again by nobody.
    assert document["applied"]["folds"] == []


def test_the_fold_says_it_is_not_durable_yet(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """Plan trap 12: while the detector keys on the node, the class re-fragments.

    A `--apply` run before the detector's keys shorten resolves the pile and the
    very next attempt mints a fresh row under the same prefix. That is not a
    defect in either story, but an operator who is not told will read the next
    day's ledger as a failed fold.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "hardening/boundary/070/us4", seen_at=_ago(1), source="det")
        _seed(conn, "hardening/boundary/071/us1", seen_at=_ago(2), source="det")
    finally:
        conn.close()

    run = apply_triage(db, specs_root)
    assert "re-fragment" in run.stdout

    document = apply_triage(db, specs_root, "--json")
    assert document.json["applied"]["fold_is_durable"] is False


# --- US3-S5 (T032): open, with a note ------------------------------------------


def test_cold_and_needs_a_human_stay_open_with_only_notes_changed(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S5 / FR-017: `open` is the answer; the annotation is the only write."""
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/long-forgotten", seen_at=_ago(60))
        _seed(conn, "ops/plain", seen_at=_ago(1), notes="Reported by hand.")
    finally:
        conn.close()

    before = {key: _row(db, key) for key in ("ops/long-forgotten", "ops/plain")}
    apply_triage(db, specs_root)

    for key, was in before.items():
        now = _row(db, key)
        assert now.status == "open", key
        assert now.occurrences == was.occurrences, key
        assert now.last_seen == was.last_seen, key
        assert now.resolution is None and now.resolved_at is None, key
        assert now.events == was.events, key
        assert now.notes != was.notes, key

    cold = _row(db, "ops/long-forgotten")
    assert cold.annotation is not None
    assert "cold" in cold.annotation

    human = _row(db, "ops/plain")
    assert human.annotation is not None
    assert "needs-human" in human.annotation
    # The note that was already there is kept: the annotation adds, never replaces.
    assert "Reported by hand." in (human.notes or "")


# --- US3-S6 (T033): a second pass costs nothing --------------------------------


def test_the_annotation_is_idempotent_and_costs_no_recurrence(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S6 / FR-018 / trap 5: annotating must not go through `report()`.

    `report()` increments occurrences, advances `last_seen` and appends a
    `finding_events` row on every call. Annotating a ledger through it would
    manufacture one phantom recurrence per finding per pass, in a ledger whose
    entire purpose is counting recurrence.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/plain", seen_at=_ago(1), notes="Reported by hand.")
    finally:
        conn.close()

    apply_triage(db, specs_root)
    first = _row(db, "ops/plain")
    apply_triage(db, specs_root)
    second = _row(db, "ops/plain")

    assert second == first
    # `Row.annotation` asserts the marker appears at most once; say it here too.
    assert (second.notes or "").count(ANNOTATION_MARKER) == 1
    assert second.occurrences == first.occurrences == 1
    assert second.last_seen == first.last_seen
    assert second.events == first.events == 1


def test_a_second_pass_reports_the_annotation_as_already_there(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """FR-018: idempotent is a fact the report states rather than hides."""
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/plain", seen_at=_ago(1))
    finally:
        conn.close()

    first = apply_triage(db, specs_root, "--json").json["applied"]
    assert first["annotated"] == ["ops/plain"]
    assert first["already_annotated"] == []

    second = apply_triage(db, specs_root, "--json").json["applied"]
    assert second["annotated"] == []
    assert second["already_annotated"] == ["ops/plain"]


# --- US3-S7 (T034): the control ------------------------------------------------


def test_nothing_declared_means_no_status_changes(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """US3-S7 / FR-019: the control, and the live store's state on the day this lands.

    No spec in this corpus carries a `fixes:` key, and no finding's key has the
    three segments fragmentation needs — so neither of the two classes `--apply`
    may write to has a member, and the sweep must come out the far side having
    changed no status at all. A `--apply` that inferred a fix from prose, from a
    landed state alone, or from a category shared by two keys fails here.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "020-names-it-in-prose",
        state="landed",
        body="Background: `ops/mentioned-only` and `ops/plain` are known.\n",
    )
    _write_spec(specs_root, "021-declares-nothing", state="landed")
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/mentioned-only", seen_at=_ago(1))
        _seed(conn, "ops/plain", seen_at=_ago(1))
        _seed(conn, "ops/long-forgotten", seen_at=_ago(60))
        # Same category, two segments: a category is not a fragmented class.
        _seed(conn, "ops/one", seen_at=_ago(2))
        _seed(conn, "ops/two", seen_at=_ago(2))
    finally:
        conn.close()

    before = _statuses(db)
    run = apply_triage(db, specs_root)
    after = _statuses(db)

    assert after == before
    assert set(after.values()) == {"open"}
    assert _resolved_keys(db) == set()

    document = apply_triage(db, specs_root, "--json").json
    assert document["applied"]["resolved"] == []
    assert document["applied"]["folds"] == []
    assert "0 resolved" in run.stdout


# --- FR-019 stated as the one predicate it is ----------------------------------


def test_only_the_resolvable_classes_are_ever_written_to(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """FR-019 over a store carrying one member of every class at once.

    The assertion is set equality, not membership: it fails both when a row that
    should have closed stayed open and when a row that should have been left
    alone was closed.
    """
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key", "ops/still-here"])
    _write_spec(
        specs_root,
        "030-mentions-in-prose",
        state="landed",
        body="Background: `ops/mentioned-only`.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")  # fixed
        _seed(conn, "ops/still-here", seen_at=_ago(1))  # seen after fix
        _seed(conn, "ops/mentioned-only", seen_at=_ago(1))  # candidate
        _seed(conn, "ops/long-forgotten", seen_at=_ago(60))  # cold
        _seed(conn, "ops/plain", seen_at=_ago(1))  # needs a human
        _seed(conn, "hardening/b/070/us4", seen_at=_ago(1), source="det")
        _seed(conn, "hardening/b/071/us1", seen_at=_ago(1), source="det")  # fragmented
    finally:
        conn.close()

    apply_triage(db, specs_root)

    assert _resolved_keys(db) == {
        "ops/leaks-a-key",
        "hardening/b/070/us4",
        "hardening/b/071/us1",
    }


def test_the_three_write_policies_partition_every_class() -> None:
    """FR-019: every class is resolvable, annotatable, or untouched — exactly one.

    This is the single predicate that reverses a whole pass, held to being
    single: a class that appeared in two of these sets would be written to twice,
    and a class in none would be silently dropped by the sweep the way a missing
    branch drops it.
    """
    assert RESOLVABLE_CLASSES | ANNOTATABLE_CLASSES | UNTOUCHED_CLASSES == set(
        CLASS_ORDER
    )
    assert not RESOLVABLE_CLASSES & ANNOTATABLE_CLASSES
    assert not RESOLVABLE_CLASSES & UNTOUCHED_CLASSES
    assert not ANNOTATABLE_CLASSES & UNTOUCHED_CLASSES


def test_apply_does_not_resolve_promoted_findings_on_the_way_past(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """FR-019 / trap 4: `--apply` writes, but only what triage classified.

    `--apply` needs a writable connection, which makes `_with_store` look
    harmless again — and it is not. That wrapper resolves every promoted finding
    whose spec attests landed, a row triage never classified and never offered to
    the predicate. Wrapping `--apply` in it would close rows the report never
    named.
    """
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
        _seed(conn, "ops/already-promoted", seen_at="2026-08-05T09:00:00Z")
        conn.execute(
            "UPDATE findings SET status = 'promoted', promoted_spec = ? "
            "WHERE key = 'ops/already-promoted'",
            (str(specs_root / "012-plugs-the-leak"),),
        )
        conn.commit()
    finally:
        conn.close()

    apply_triage(db, specs_root)

    assert _row(db, "ops/leaks-a-key").status == "resolved"
    assert _row(db, "ops/already-promoted").status == "promoted"


def test_an_already_resolved_row_is_not_reopened_or_re_annotated(
    tmp_path: Path, apply_triage: Callable[..., Run]
) -> None:
    """FR-004: only open and regressed rows are classified, so only they are written.

    The resolved row here is also named by a landed spec's prose, which is the
    shape that would tempt a sweep written over `list_findings` rather than over
    the classification.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "020-names-it",
        state="landed",
        body="Background: `ops/gone`.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/gone", seen_at=_ago(3))
        resolve(conn, "ops/gone", reason="closed by hand", resolved_at=_ago(2))
    finally:
        conn.close()

    before = _row(db, "ops/gone")
    apply_triage(db, specs_root)

    assert _row(db, "ops/gone") == before
    assert before.resolution == "closed by hand"
