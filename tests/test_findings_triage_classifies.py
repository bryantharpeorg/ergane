"""US2: `ergane findings triage` sorts a ledger into classes it can prove.

Every fixture here is *supplied* — a store built with `connect()` on a
`tmp_path`, and a specs corpus built as files under `tmp_path`, sometimes inside
a throwaway git repository (plan trap 13). Nothing in this file opens
`.factory/`, the running factory's `doctor.db`, or this repository's real
`specs/`: the first reads production evidence, and the last fails the week a
spec's state flips.

The controls carry as much weight as the positives (plan trap 15). A classifier
that answered "needs a human" for every row would satisfy every positive
assertion about *reachability* and none of these:

- `test_declared_but_seen_since_is_not_fixed` — a declaration plus a later
  sighting is a live regression, not a closable row (US2-S2, FR-006).
- `test_undated_landing_is_never_fixed` — an undated claim is not a proof
  (US2-S3, FR-007, trap 2).
- `test_prose_naming_a_deeper_key_is_not_a_mention` — segment-bounded matching,
  never a bare substring (US2-S4, FR-009, trap 6).
- `test_a_lone_key_and_two_segment_keys_are_not_fragmented` — most keys in the
  store are `category/slug` and must form no group at all (US2-S6, trap 7).
- `test_cold_is_old_and_singular` — carries both halves in one test (US2-S7).
- `test_triage_without_apply_does_not_change_one_byte` — hashes the file
  (US2-S8, FR-013, trap 4).
"""

from __future__ import annotations

import hashlib
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
from factory.doctor.store import connect, report, resolve


# --- harness ------------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    def keys_in(self, triage_class: str) -> list[str]:
        return [entry["key"] for entry in self.json["classes"][triage_class]]

    def entry(self, triage_class: str, key: str) -> dict[str, Any]:
        for candidate in self.json["classes"][triage_class]:
            if candidate["key"] == key:
                return candidate
        raise AssertionError(
            f"{key!r} is not in class {triage_class!r}; it is in "
            f"{self.class_of(key)!r}"
        )

    def class_of(self, key: str) -> str | None:
        for name, entries in self.json["classes"].items():
            if any(entry["key"] == key for entry in entries):
                return name
        return None


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
def triage() -> Callable[..., Run]:
    """Run `ergane findings triage` over a supplied store and a supplied corpus."""

    def _caller(db: Path, specs_root: Path, *extra: str) -> Run:
        run = _invoke(
            [
                "findings",
                "triage",
                "--db",
                str(db),
                "--specs-root",
                str(specs_root),
                *extra,
            ]
        )
        assert run.code == 0, f"triage failed: {run.stderr}"
        return run

    return _caller


def _seed(
    conn: Any,
    key: str,
    *,
    seen_at: str,
    source: str = "probe",
    severity: Severity = Severity.WARNING,
) -> None:
    """Report one finding once, so it lands `open` with `occurrences` 1."""
    report(
        conn,
        Finding(
            key=key,
            category=key.split("/")[0],
            severity=severity,
            status=Status.OPEN,
            summary=f"summary for {key}",
            refs=[],
            notes=None,
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


def _store(tmp_path: Path, name: str = "doctor.db") -> Path:
    return tmp_path / "store" / name


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
    plan: str | None = None,
) -> Path:
    directory = specs_root / spec_dir
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"state: {state}"]
    if fixes is not None:
        lines.append("fixes:")
        lines.extend(f"  - {key}" for key in fixes)
    lines.extend(["---", "", body])
    (directory / "spec.md").write_text("\n".join(lines), encoding="utf-8")
    if plan is not None:
        (directory / "plan.md").write_text(plan, encoding="utf-8")
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


def _landing_corpus(
    tmp_path: Path,
    *,
    fixes: list[str],
    landed_at: str = "2026-08-10T00:00:00+00:00",
    amended_at: str = "2026-08-18T00:00:00+00:00",
) -> Path:
    """A git repo whose spec was drafted, then attested landed, then amended.

    The amendment is the point: `git log -1` would date the landing at
    `amended_at`, and `git log --reverse` — the first commit that introduced
    `state: landed` — dates it at `landed_at` (plan trap 3). Every date
    assertion below is only meaningful because these two disagree.
    """
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
    _git(repo, "commit", "-m", "attest landed", when=landed_at)

    _write_spec(
        specs_root,
        "012-plugs-the-leak",
        state="landed",
        fixes=fixes,
        body="A later amendment that is not a second landing.\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "amend after landing", when=amended_at)

    return specs_root


# --- US2-S1 (T010): a declaration plus a date is a proof ----------------------


def test_declared_and_unseen_since_is_fixed_and_names_the_spec(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S1 / FR-005 / FR-012: fixed, and the report names spec and date."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == ["ops/leaks-a-key"]

    entry = run.entry("fixed", "ops/leaks-a-key")
    assert entry["specs"] == ["012-plugs-the-leak"]
    # FR-012: the landing date, and the *first* attestation's date (trap 3) —
    # not the later amendment's, which `git log -1` would have returned.
    assert entry["landing_date"].startswith("2026-08-10")

    human = triage(db, specs_root)
    assert "012-plugs-the-leak" in human.stdout
    assert "2026-08-10" in human.stdout


# --- US2-S2 (T011): the control that matters most -----------------------------


def test_declared_but_seen_since_is_not_fixed(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S2 / FR-006: the same declaration, a later sighting, no closure."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-12T09:00:00Z")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == []
    assert run.keys_in("seen-after-fix") == ["ops/leaks-a-key"]

    entry = run.entry("seen-after-fix", "ops/leaks-a-key")
    assert entry["specs"] == ["012-plugs-the-leak"]
    assert entry["landing_date"].startswith("2026-08-10")


def test_last_seen_exactly_at_the_landing_commit_is_fixed(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """FR-005 says *at or before*, so the boundary itself closes the row."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-10T00:00:00Z")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == ["ops/leaks-a-key"]


# --- US2-S3 (T012): an undated claim is not a proof ---------------------------


def test_undated_landing_is_never_fixed(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S3 / FR-007 / trap 2: `state: landed` with no commit that says so.

    The corpus here is a plain directory, not a git repository — the same
    evidence a working-tree flip that was never committed leaves behind. No
    commit introduces the attestation, so nothing can date it, and the row goes
    to the human rather than to the closable pile.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "013-says-it-landed",
        state="landed",
        fixes=["ops/leaks-a-key"],
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == []
    assert run.keys_in("seen-after-fix") == []
    assert run.keys_in("needs-human") == ["ops/leaks-a-key"]

    entry = run.entry("needs-human", "ops/leaks-a-key")
    assert entry["specs"] == ["013-says-it-landed"]
    assert entry["landing_date"] is None
    assert "date" in entry["reason"]


# --- US2-S4 (T013): prose is a candidate, never a declaration -----------------


def test_prose_names_a_candidate_and_lists_every_naming_spec(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S4 / FR-008 / trap 1: two landed specs name it; neither declares it."""
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "020-fixes-it-maybe",
        state="landed",
        body="This epic was filed against `ops/leaks-a-key` and closes it.\n",
    )
    _write_spec(
        specs_root,
        "021-mentions-it-too",
        state="landed",
        body="Out of scope for this epic.\n",
        plan="`ops/leaks-a-key` is background, NOT fixed here.\n",
    )
    # Not landed, so its prose is not evidence about a landing at all.
    _write_spec(
        specs_root,
        "022-still-drafting",
        state="draft",
        body="`ops/leaks-a-key` will be handled one day.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at=_ago(1))
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == []
    assert run.keys_in("candidate") == ["ops/leaks-a-key"]

    entry = run.entry("candidate", "ops/leaks-a-key")
    assert entry["specs"] == ["020-fixes-it-maybe", "021-mentions-it-too"]

    human = triage(db, specs_root)
    assert "020-fixes-it-maybe" in human.stdout
    assert "021-mentions-it-too" in human.stdout


def test_prose_naming_a_deeper_key_is_not_a_mention(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """FR-008 / FR-009 / trap 6: segment-bounded, never a bare substring.

    `ops/leaks-a-key` is a strict prefix of `ops/leaks-a-key/070/us4`, and a
    naive `key in text` test reads the second as a mention of the first. That
    defect is invisible today and arrives whole the day US5 shortens the
    detector's keys.
    """
    specs_root = tmp_path / "specs"
    _write_spec(
        specs_root,
        "023-names-a-deeper-key",
        state="landed",
        body="Only `ops/leaks-a-key/070/us4` is named here, and `x-ops/leaks-a-key`.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at=_ago(1))
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("candidate") == []
    assert run.keys_in("needs-human") == ["ops/leaks-a-key"]


def test_a_key_named_only_in_a_frontmatter_comment_still_names_its_spec(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """FR-008: *every* spec whose prose names it, including the attest block.

    Measured on this repository's own corpus on 2026-08-21: two landed specs
    name `interpreter/ci-failure-never-reaches-an-agent` solely inside the
    `# ATTESTED landed …` comment block their frontmatter carries. A scan that
    read the body only dropped both, and under-reported the naming specs FR-008
    requires be listed in full.
    """
    specs_root = tmp_path / "specs"
    directory = specs_root / "040-attested-with-a-note"
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(
        "---\n"
        "state: landed\n"
        "# ATTESTED landed 2026-08-19. Bookkeeping only; the finding\n"
        "#   ops/leaks-a-key  is regressed and stays open.\n"
        "---\n"
        "\nThe body names nothing.\n",
        encoding="utf-8",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at=_ago(1))
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("candidate") == ["ops/leaks-a-key"]
    assert run.entry("candidate", "ops/leaks-a-key")["specs"] == [
        "040-attested-with-a-note"
    ]
    # And still a candidate, never fixed: the note says the opposite of fixed.
    assert run.keys_in("fixed") == []


def test_a_declared_key_is_never_also_a_candidate(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """FR-004 / FR-008: the declared class and the prose class stay apart."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
    _write_spec(
        specs_root,
        "024-also-mentions-it",
        state="landed",
        body="Background: `ops/leaks-a-key`.\n",
    )
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/leaks-a-key", seen_at="2026-08-05T09:00:00Z")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.keys_in("fixed") == ["ops/leaks-a-key"]
    assert run.keys_in("candidate") == []


# --- US2-S5 (T014): one fragmented class --------------------------------------


def test_prefix_sharing_keys_are_one_fragmented_class(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S5 / FR-009: one class, naming the shared prefix and the count."""
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(
            conn,
            "hardening/agent-worktree-boundary/070/us4",
            seen_at=_ago(1),
            source="boundary-detector",
        )
        _seed(
            conn,
            "hardening/agent-worktree-boundary/071/us1",
            seen_at=_ago(2),
            source="boundary-detector",
        )
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    classes = run.json["fragmented_classes"]
    assert len(classes) == 1
    assert classes[0]["prefix"] == "hardening/agent-worktree-boundary"
    assert classes[0]["source"] == "boundary-detector"
    assert classes[0]["members"] == 2
    assert classes[0]["keys"] == [
        "hardening/agent-worktree-boundary/070/us4",
        "hardening/agent-worktree-boundary/071/us1",
    ]
    assert sorted(run.keys_in("fragmented")) == classes[0]["keys"]

    human = triage(db, specs_root)
    assert "hardening/agent-worktree-boundary" in human.stdout
    assert "2" in human.stdout


# --- US2-S6 (T015): scenario 5's control --------------------------------------


def test_a_lone_key_and_two_segment_keys_are_not_fragmented(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S6 / trap 7: category/slug is not a class, and one member is not a group.

    A rule that split on the *last* slash would put `ops/one` and `ops/two`
    into a group called `ops` and report a fragmented class that is not one.
    A rule that dropped the `source` condition would group the last pair.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/one", seen_at=_ago(1), source="probe")
        _seed(conn, "ops/two", seen_at=_ago(1), source="probe")
        _seed(conn, "hardening/agent-worktree-boundary/070/us4", seen_at=_ago(1))
        _seed(conn, "verify/judge/a", seen_at=_ago(1), source="alpha")
        _seed(conn, "verify/judge/b", seen_at=_ago(1), source="beta")
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.json["fragmented_classes"] == []
    assert run.keys_in("fragmented") == []
    assert run.json["counts"]["fragmented"] == 0


# --- US2-S7 (T016): cold is old *and* singular --------------------------------


def test_cold_is_old_and_singular(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S7 / FR-010: both halves in one test, plus the threshold's default."""
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/long-forgotten", seen_at=_ago(60))
        _seed(conn, "ops/seen-yesterday", seen_at=_ago(1))
        # Old, but it has happened twice: recurrence is the opposite of cold.
        _seed(conn, "ops/old-but-recurring", seen_at=_ago(60))
        _seed(conn, "ops/old-but-recurring", seen_at=_ago(59))
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    assert run.json["cold_days"] == 14
    assert run.keys_in("cold") == ["ops/long-forgotten"]
    assert run.class_of("ops/seen-yesterday") == "needs-human"
    assert run.class_of("ops/old-but-recurring") == "needs-human"


def test_the_cold_threshold_is_operator_settable(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """FR-010: the threshold is a flag, and moving it moves the class."""
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    conn = connect(db)
    try:
        _seed(conn, "ops/twenty-days-old", seen_at=_ago(20))
    finally:
        conn.close()

    assert triage(db, specs_root, "--json").keys_in("cold") == ["ops/twenty-days-old"]
    widened = triage(db, specs_root, "--cold-days", "90", "--json")
    assert widened.json["cold_days"] == 90
    assert widened.keys_in("cold") == []


# --- US2-S8 (T017): the report changes nothing --------------------------------


def test_triage_without_apply_does_not_change_one_byte(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S8 / FR-013 / trap 4: hash the store file before and after.

    The store is seeded with a *promoted* finding whose spec attests landed —
    exactly the row `_with_store`'s `_resolve_promoted_findings` sweep would
    resolve on the way past. Inheriting that wrapper is the invisible failure
    this test exists to make visible.
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

    def digest() -> str:
        return hashlib.sha256(db.read_bytes()).hexdigest()

    before = digest()
    triage(db, specs_root)
    between = digest()
    triage(db, specs_root, "--json")
    after = digest()

    assert before == between == after

    # And the row the sweep would have closed is still promoted.
    conn = connect(db)
    try:
        status = conn.execute(
            "SELECT status FROM findings WHERE key = 'ops/already-promoted'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "promoted"


# --- US2-S9 (T018): no row is silently dropped --------------------------------


def test_class_counts_sum_to_the_open_and_regressed_total(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """US2-S9 / FR-004 / FR-011: every open and regressed row lands in one class."""
    specs_root = _landing_corpus(tmp_path, fixes=["ops/leaks-a-key"])
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
        _seed(conn, "ops/mentioned-only", seen_at=_ago(1))  # candidate
        _seed(conn, "ops/long-forgotten", seen_at=_ago(60))  # cold
        _seed(conn, "ops/plain", seen_at=_ago(1))  # needs a human
        _seed(conn, "hardening/b/070/us4", seen_at=_ago(1), source="det")
        _seed(conn, "hardening/b/071/us1", seen_at=_ago(1), source="det")  # fragmented
        # Neither open nor regressed: these must not be counted at all.
        _seed(conn, "ops/gone", seen_at=_ago(3))
        resolve(conn, "ops/gone", reason="done", resolved_at=_ago(2))
        _seed(conn, "ops/promoted-away", seen_at=_ago(3))
        conn.execute(
            "UPDATE findings SET status = 'promoted' WHERE key = 'ops/promoted-away'"
        )
        conn.commit()
        # A regressed row *is* counted.
        _seed(conn, "ops/came-back", seen_at=_ago(5))
        resolve(conn, "ops/came-back", reason="thought so", resolved_at=_ago(4))
        _seed(conn, "ops/came-back", seen_at=_ago(1))
    finally:
        conn.close()

    run = triage(db, specs_root, "--json")
    document = run.json

    assert document["total"] == 7
    assert sum(document["counts"].values()) == 7
    assert document["classified"] == 7

    classified = [
        entry["key"] for entries in document["classes"].values() for entry in entries
    ]
    assert sorted(classified) == sorted(
        [
            "ops/leaks-a-key",
            "ops/mentioned-only",
            "ops/long-forgotten",
            "ops/plain",
            "hardening/b/070/us4",
            "hardening/b/071/us1",
            "ops/came-back",
        ]
    )
    # Exactly one class each — no key appears twice.
    assert len(classified) == len(set(classified))

    human = triage(db, specs_root)
    assert "7 classified = 7 open and regressed" in human.stdout


def test_the_report_says_which_tree_it_read_spec_state_from(
    tmp_path: Path, triage: Callable[..., Run]
) -> None:
    """Spec Assumptions / T027: state is read from the operator's working tree.

    That is a known defect class of its own
    (`roadmap/dispatch-is-decided-by-the-operators-working-tree`), so the report
    is explicit about it rather than leaving the operator to assume the branch.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    db = _store(tmp_path)
    connect(db).close()

    human = triage(db, specs_root)
    assert "working tree" in human.stdout
    assert str(specs_root) in human.stdout

    document = triage(db, specs_root, "--json").json
    assert document["spec_state_source"] == "working tree"
    assert document["specs_root"] == str(specs_root)
