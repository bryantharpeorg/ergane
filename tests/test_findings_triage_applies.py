"""US3: what `ergane findings triage --apply` may enact, and what it may not.

US2 sorts every open and regressed finding into exactly one class. This suite is
about the handful of lines that decide which of those classes reach the store —
and, carrying at least as much weight, which do not. Three of the seven
scenarios are silences:

- `test_a_prose_candidate_is_untouched` — a landed spec *naming* a key is not a
  landed spec *declaring* it. On the corpus this spec was written against, one
  key was named by six specs and one of the six said the finding had regressed;
  a rule that read prose as a declaration would have closed a live defect
  (US3-S2, FR-019, plan trap 1).
- `test_a_finding_seen_after_its_fix_is_untouched` — a declaration plus a later
  sighting is the top of the operator's queue, not the bottom of the closable
  pile (US3-S3, FR-015).
- `test_nothing_declared_changes_no_status` — the control, and the state of the
  live findings store on the day this lands: no spec in it declares a `fixes:`
  at all, so a `--apply` that closed anything would be inferring a fix from
  something that is not a declaration (US3-S7).

The classification is *supplied*, not computed: each test hands the sweep the
rows a classifier would have produced, because what the sweep does with a class
is exactly what this story is about, and re-deriving the class first would make
every one of these assertions depend on a specs corpus, a git history and a
clock. `Classified` and `Fragmented` carry the same four and four fields
`TriagedFinding` and `FragmentedClass` do, and the class names are
`TriageClass`'s values verbatim.

The store, by contrast, is real: `connect()` on a `tmp_path`, written through
the same functions production writes through, and read back through
`get_finding` and `list_events`. Nothing here opens `.factory/`, the running
factory's `doctor.db`, or this repository's real `specs/` (plan trap 13).

A silence is only a control if it can be broken, so each was, by flipping one
thing in the code under these same fixtures (plan trap 15). Pasted, not
described:

    ### mutation A — "candidate" and "seen-after-fix" added to RESOLVABLE
    FAILED test_a_prose_candidate_is_untouched
    FAILED test_a_finding_seen_after_its_fix_is_untouched
    FAILED test_nothing_declared_changes_no_status
    FAILED test_only_two_classes_are_resolvable
    4 failed, 11 passed

    ### mutation B — annotate() also bumps occurrences and last_seen (trap 5)
    FAILED test_cold_and_needs_a_human_stay_open_with_only_notes_changed
    FAILED test_a_second_pass_changes_nothing
    FAILED test_nothing_declared_changes_no_status
    FAILED test_annotate_writes_the_note_and_nothing_else
    4 failed, 11 passed

    ### mutation C — the fold's resolution drops the prefix and the count
    FAILED test_every_member_of_a_fragmented_class_is_folded
    1 failed, 14 passed

Mutation A is why the control's rows carry the specs their classes would really
name: with `specs=()` everywhere it passed the mutation, because there was
nothing to write as a resolution — a control that could not fail.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

import pytest

from factory.doctor.models import Finding, FindingEvent, Status
from factory.doctor.store import (
    ANNOTATION_MARKER,
    annotate,
    connect,
    get_finding,
    list_events,
)
from factory.doctor.triage_apply import (
    REFRAGMENT_NOTICE,
    RESOLVABLE,
    Application,
    apply_triage,
    render,
    to_document,
)

#: `TriageClass`'s values, verbatim. Named here so a reader can see at a glance
#: that all six are exercised, and so a rename in the classifier fails these
#: tests loudly rather than quietly reclassifying a row into a branch that
#: writes.
FIXED = "fixed"
SEEN_AFTER_FIX = "seen-after-fix"
FRAGMENTED = "fragmented"
CANDIDATE = "candidate"
COLD = "cold"
NEEDS_HUMAN = "needs-human"

#: The moment every pass in this file writes, so a resolution's timestamp is an
#: assertion rather than a race with the clock.
NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Classified:
    """One classified row, in the shape `TriagedFinding` presents to the sweep."""

    key: str
    triage_class: str
    reason: str = "because the classifier said so"
    specs: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class Fragmented:
    """One fragmented class, in the shape `FragmentedClass` presents."""

    prefix: str
    source: str
    keys: Sequence[str]

    @property
    def members(self) -> int:
        return len(self.keys)


# --- the store, real and supplied ---------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "store" / "doctor.db")
    try:
        yield conn
    finally:
        conn.close()


def _seed(
    conn: sqlite3.Connection,
    key: str,
    *,
    seen_at: str = "2026-08-05T09:00:00Z",
    source: str = "probe",
    notes: str | None = None,
    occurrences: int = 1,
) -> None:
    """Insert one finding with the row shape the test wants, and one event.

    Deliberately not through `report()`: that is the recurrence machine, and a
    row seeded at three occurrences through it would also carry three events for
    every assertion here to have to discount.
    """
    with conn:
        conn.execute(
            """
            INSERT INTO findings (
                key, category, severity, status, summary, refs, notes, source,
                occurrences, first_seen, last_seen, promoted_spec, resolved_at,
                resolution
            ) VALUES (?, ?, 'warning', 'open', ?, '[]', ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                key,
                key.split("/")[0],
                f"summary for {key}",
                notes,
                source,
                occurrences,
                seen_at,
                seen_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO finding_events (finding_key, seen_at, source, severity, kind)
            VALUES (?, ?, ?, 'warning', 'reported')
            """,
            (key, seen_at, source),
        )


def _row(conn: sqlite3.Connection, key: str) -> Finding:
    found = get_finding(conn, key)
    assert found is not None, f"finding {key!r} not found"
    return found


def _events(conn: sqlite3.Connection, key: str) -> list[FindingEvent]:
    return list_events(conn, key)


def _snapshot(conn: sqlite3.Connection, key: str) -> tuple:
    """Every column `--apply` is forbidden to move on a silent class."""
    row = _row(conn, key)
    return (
        row.status,
        row.occurrences,
        row.last_seen,
        row.notes,
        row.resolution,
        row.resolved_at,
        _events(conn, key),
    )


def _apply(
    conn: sqlite3.Connection,
    findings: Sequence[Classified],
    fragmented: Sequence[Fragmented] = (),
) -> Application:
    return apply_triage(conn, findings, fragmented, now=NOW)


# --- US3-S1 (T028): a declaration that landed closes the row ------------------


def test_a_fixed_finding_is_resolved_naming_its_spec(
    store: sqlite3.Connection,
) -> None:
    """US3-S1 / FR-014: status `resolved`, resolution = the declaring spec dir."""
    _seed(store, "ops/leaks-a-key")

    application = _apply(
        store,
        [
            Classified(
                key="ops/leaks-a-key",
                triage_class=FIXED,
                reason="declared fixed by '012-plugs-the-leak', which landed 2026-08-10",
                specs=("012-plugs-the-leak",),
            )
        ],
    )

    row = _row(store, "ops/leaks-a-key")
    assert row.status is Status.RESOLVED
    assert row.resolution == "012-plugs-the-leak"
    assert row.resolved_at == "2026-08-21T12:00:00Z"

    # The close leaves a trail: `resolve_by_spec` appends a `resolved` event
    # sourced to the roadmap rather than to an operator, which is what makes a
    # swept resolution tellable from a hand-typed one months later.
    kinds = [(event.kind, event.source) for event in _events(store, "ops/leaks-a-key")]
    assert kinds == [("reported", "probe"), ("resolved", "roadmap")]

    assert [item.key for item in application.resolved] == ["ops/leaks-a-key"]
    assert "012-plugs-the-leak" in render(application)


# --- US3-S2 (T029): naming is not fixing --------------------------------------


def test_a_prose_candidate_is_untouched(store: sqlite3.Connection) -> None:
    """US3-S2 / FR-019 / trap 1: prose is not a declaration and never closes a row."""
    _seed(store, "ops/mentioned-only", notes="a probe wrote this", occurrences=3)
    before = _snapshot(store, "ops/mentioned-only")

    application = _apply(
        store,
        [
            Classified(
                key="ops/mentioned-only",
                triage_class=CANDIDATE,
                reason="named in the prose of landed spec '030-mentions-in-prose'",
                specs=("030-mentions-in-prose",),
            )
        ],
    )

    assert _snapshot(store, "ops/mentioned-only") == before
    assert _row(store, "ops/mentioned-only").status is Status.OPEN
    assert application.writes == 0
    assert application.untouched[CANDIDATE] == 1


# --- US3-S3 (T030): a re-sighting is the top of the queue ---------------------


def test_a_finding_seen_after_its_fix_is_untouched(store: sqlite3.Connection) -> None:
    """US3-S3 / FR-015: status, occurrences, `last_seen` and the trail all unchanged.

    The declaring spec is right there in the row's classification — this is the
    one class where `--apply` is holding a declaration and must still refuse.
    """
    _seed(store, "ops/leaks-a-key", seen_at="2026-08-18T09:00:00Z", occurrences=4)
    before = _snapshot(store, "ops/leaks-a-key")

    application = _apply(
        store,
        [
            Classified(
                key="ops/leaks-a-key",
                triage_class=SEEN_AFTER_FIX,
                reason="declared fixed by '012-plugs-the-leak' — but seen again since",
                specs=("012-plugs-the-leak",),
            )
        ],
    )

    after = _snapshot(store, "ops/leaks-a-key")
    assert after == before
    assert _row(store, "ops/leaks-a-key").status is Status.OPEN
    assert _row(store, "ops/leaks-a-key").occurrences == 4
    assert len(_events(store, "ops/leaks-a-key")) == 1
    assert application.writes == 0
    assert application.untouched[SEEN_AFTER_FIX] == 1


# --- US3-S4 (T031): the fold ---------------------------------------------------


def test_every_member_of_a_fragmented_class_is_folded(
    store: sqlite3.Connection,
) -> None:
    """US3-S4 / FR-016: every member resolved, naming the prefix and the count."""
    members = (
        "hardening/agent-worktree-boundary/070/us4",
        "hardening/agent-worktree-boundary/070/us5",
        "hardening/agent-worktree-boundary/071/us1",
    )
    for key in members:
        _seed(store, key, source="boundary-detector")

    group = Fragmented(
        prefix="hardening/agent-worktree-boundary",
        source="boundary-detector",
        keys=members,
    )
    application = _apply(
        store,
        [Classified(key=key, triage_class=FRAGMENTED) for key in members],
        [group],
    )

    for key in members:
        row = _row(store, key)
        assert row.status is Status.RESOLVED, f"{key} was not folded"
        assert "hardening/agent-worktree-boundary" in (row.resolution or "")
        assert "3" in (row.resolution or ""), row.resolution

    report = render(application)
    assert "hardening/agent-worktree-boundary" in report
    # And the fold is honest about its own half-life until the detector stops
    # minting a key per node (plan trap 12).
    assert REFRAGMENT_NOTICE in report
    assert to_document(application)["surviving_class_keys"] == [
        "hardening/agent-worktree-boundary"
    ]


# --- US3-S5 (T032): cold and needs-a-human stay open --------------------------


def test_cold_and_needs_a_human_stay_open_with_only_notes_changed(
    store: sqlite3.Connection,
) -> None:
    """US3-S5 / FR-017: the annotation is the whole of what `--apply` may do here."""
    _seed(store, "ops/long-quiet", seen_at="2026-05-01T09:00:00Z")
    _seed(store, "ops/still-live", seen_at="2026-08-20T09:00:00Z", occurrences=5)
    before = {key: _snapshot(store, key) for key in ("ops/long-quiet", "ops/still-live")}

    _apply(
        store,
        [
            Classified(
                key="ops/long-quiet",
                triage_class=COLD,
                reason="seen once, on 2026-05-01, more than 14 days ago",
            ),
            Classified(
                key="ops/still-live",
                triage_class=NEEDS_HUMAN,
                reason="no landed spec declares or names it, and it is not cold",
            ),
        ],
    )

    for key in ("ops/long-quiet", "ops/still-live"):
        row = _row(store, key)
        was_status, was_occurrences, was_last_seen, was_notes, _, _, was_events = before[
            key
        ]
        assert row.status is Status.OPEN is was_status
        assert row.resolution is None
        assert row.resolved_at is None
        assert row.occurrences == was_occurrences
        assert row.last_seen == was_last_seen
        assert _events(store, key) == was_events
        assert row.notes != was_notes
        assert ANNOTATION_MARKER in (row.notes or "")

    assert "cold" in (_row(store, "ops/long-quiet").notes or "")
    assert "needs-human" in (_row(store, "ops/still-live").notes or "")


# --- US3-S6 (T033): a second pass is a no-op ----------------------------------


def test_a_second_pass_changes_nothing(store: sqlite3.Connection) -> None:
    """US3-S6 / FR-018 / trap 5: idempotent, and never through `report()`.

    `report()` would increment `occurrences`, advance `last_seen` and append an
    event on every pass — one phantom recurrence per annotated row, in the one
    column the ledger exists to count.
    """
    _seed(store, "ops/long-quiet", seen_at="2026-05-01T09:00:00Z", notes="probe note")
    classification = [
        Classified(
            key="ops/long-quiet",
            triage_class=COLD,
            reason="seen once, on 2026-05-01, more than 14 days ago",
        )
    ]

    first_pass = _apply(store, classification)
    first = _snapshot(store, "ops/long-quiet")
    second_pass = _apply(store, classification)
    second = _snapshot(store, "ops/long-quiet")

    assert second == first
    notes = _row(store, "ops/long-quiet").notes or ""
    assert notes.count(ANNOTATION_MARKER) == 1
    assert "probe note" in notes
    assert _row(store, "ops/long-quiet").occurrences == 1
    assert len(_events(store, "ops/long-quiet")) == 1

    assert first_pass.writes == 1
    assert second_pass.writes == 0
    assert second_pass.already_annotated == ["ops/long-quiet"]


# --- US3-S7 (T034): the control ------------------------------------------------


def test_nothing_declared_changes_no_status(store: sqlite3.Connection) -> None:
    """US3-S7: a store nothing declares comes out with every status intact.

    This is the live ledger's shape today: no `fixes:` anywhere in the corpus,
    so the classifier can produce candidates, cold rows and residue — and not
    one closable row. The pass must therefore close nothing at all.
    """
    # Each row carries the specs its class would really name — the candidate the
    # specs whose prose mentions it, the re-sighting its declaring spec. A
    # control whose rows named no spec would pass even with those classes made
    # resolvable, because there would be nothing to write as a resolution.
    rows = {
        "ops/mentioned-only": Classified(
            key="ops/mentioned-only",
            triage_class=CANDIDATE,
            specs=("030-mentions-in-prose", "031-names-a-few"),
        ),
        "ops/long-quiet": Classified(key="ops/long-quiet", triage_class=COLD),
        "ops/still-live": Classified(key="ops/still-live", triage_class=NEEDS_HUMAN),
        "ops/leaks-a-key": Classified(
            key="ops/leaks-a-key",
            triage_class=SEEN_AFTER_FIX,
            specs=("012-plugs-the-leak",),
        ),
    }
    for key in rows:
        _seed(store, key, occurrences=2)
    before = {key: _snapshot(store, key) for key in rows}

    application = _apply(store, list(rows.values()))

    for key in rows:
        row = _row(store, key)
        assert row.status is Status.OPEN, f"{key} changed status"
        assert row.resolution is None
        assert row.resolved_at is None
        was = before[key]
        assert (row.occurrences, row.last_seen) == (was[1], was[2])
        assert _events(store, key) == was[6]

    assert application.resolved == []
    assert application.folded == []
    assert to_document(application)["surviving_class_keys"] == []


# --- FR-019: the rule is one tuple, and an unknown class is refused -----------


def test_only_two_classes_are_resolvable(store: sqlite3.Connection) -> None:
    """FR-019, stated once: the tuple an operator audits, and its whole content."""
    assert RESOLVABLE == ("fixed", "fragmented")


def test_a_class_with_no_rule_is_refused(store: sqlite3.Connection) -> None:
    """A seventh class must default to doing nothing, not to the nearest branch."""
    _seed(store, "ops/from-the-future")
    before = _snapshot(store, "ops/from-the-future")

    application = _apply(
        store,
        [Classified(key="ops/from-the-future", triage_class="not-a-class-yet")],
    )

    assert _snapshot(store, "ops/from-the-future") == before
    assert application.writes == 0
    assert application.refused == ["ops/from-the-future"]
    assert "ops/from-the-future" in render(application)


def test_a_fixed_row_with_no_declaring_spec_is_refused(
    store: sqlite3.Connection,
) -> None:
    """A resolution nobody could check is not written; the row is named instead."""
    _seed(store, "ops/unattributed")

    application = _apply(
        store, [Classified(key="ops/unattributed", triage_class=FIXED, specs=())]
    )

    assert _row(store, "ops/unattributed").status is Status.OPEN
    assert application.refused == ["ops/unattributed"]


# --- annotate: the one new store function (T038, FR-017, FR-018) --------------


def test_annotate_writes_the_note_and_nothing_else(store: sqlite3.Connection) -> None:
    """FR-018: notes change; occurrences, `last_seen` and the trail do not."""
    _seed(store, "ops/cold-one", seen_at="2026-06-01T10:00:00Z", occurrences=3)
    before = _row(store, "ops/cold-one")

    assert annotate(store, "ops/cold-one", annotation="cold: seen once") is True

    after = _row(store, "ops/cold-one")
    assert "cold: seen once" in (after.notes or "")
    assert after.status is Status.OPEN
    assert after.occurrences == before.occurrences
    assert after.last_seen == before.last_seen
    assert after.first_seen == before.first_seen
    assert after.resolved_at is None
    assert after.resolution is None
    assert len(_events(store, "ops/cold-one")) == 1


def test_annotate_keeps_the_note_a_human_wrote(store: sqlite3.Connection) -> None:
    _seed(store, "ops/has-notes", notes="the probe saw this at 03:00")

    annotate(store, "ops/has-notes", annotation="needs a human")

    notes = _row(store, "ops/has-notes").notes or ""
    assert "the probe saw this at 03:00" in notes
    assert "needs a human" in notes


def test_annotate_twice_writes_one_annotation(store: sqlite3.Connection) -> None:
    """FR-018: idempotent, and the second pass reports that it wrote nothing."""
    _seed(store, "ops/twice", notes="original")

    assert annotate(store, "ops/twice", annotation="cold: seen once") is True
    first = _row(store, "ops/twice").notes or ""
    assert annotate(store, "ops/twice", annotation="cold: seen once") is False
    second = _row(store, "ops/twice").notes or ""

    assert first == second
    assert first.count("cold: seen once") == 1


def test_annotate_replaces_a_stale_annotation(store: sqlite3.Connection) -> None:
    """A row's class can change between passes; its notes must not accumulate."""
    _seed(store, "ops/moved", notes="a human wrote this")

    annotate(store, "ops/moved", annotation="cold: seen once")
    annotate(store, "ops/moved", annotation="needs a human: nothing declares it")

    notes = _row(store, "ops/moved").notes or ""
    assert "a human wrote this" in notes
    assert "cold: seen once" not in notes
    assert notes.count("needs a human: nothing declares it") == 1


def test_annotate_unknown_key_is_a_no_op(store: sqlite3.Connection) -> None:
    assert annotate(store, "ops/never-reported", annotation="x") is False
