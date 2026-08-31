"""120/US3: the roadmap dial is reconciled against the file, not the rewrite.

US1 stopped init rewriting a valid manifest and US2 made the rewrite that
remains carry everything forward. What is left is the *comparison*: init reads a
manifest back to work out what schedule this repository declares, and FR-010
says the thing it reads must be the operator's manifest rather than whatever
init itself has just put on disk — or, as this file found, a path init merely
assumed the manifest would be at.

Three claims, one per acceptance scenario, and a control beside each:

- **a disagreement is reported** (US3-S1). The dial the operator declared is
  what the live schedule is compared against, and a schedule that differs is
  named as differing. Two vehicles: the ordinary one, which US1 already fixed
  and which is pinned here so it stays fixed, and
  `test_a_legacy_named_manifest_is_still_the_manifest_it_reconciles_against`,
  which is red before this story. `_schedule` loaded `repo_root /
  MANIFEST_NAME` — a hardcoded name, not `resolve_manifest_path`, which is what
  `_existing_manifest` and `ergane init --check` both ask — so on a repository
  whose committed manifest is still called `factory.yaml` the reconciliation
  read a file that does not exist and reported `failed: the manifest just
  written did not load`. The check two lines below it in the same transcript
  reported the drift correctly, which is the shape of the defect: one verb, two
  readers, two answers about one file.
- **the object compared against is the manifest init judged** (trap 7), proven
  at the seam by handing `_schedule` a kept manifest that says one thing while
  the bytes on disk say another. An implementation that re-reads the file after
  the write passes every test above this one and fails this.
- **agreement is reported** (US3-S2) — the control on the first claim. Without
  it a `_schedule` that reported disagreement unconditionally would pass US3-S1.
- **an undeclared dial says so** (US3-S3). `desired_for_repo` substitutes
  `RoadmapDials()` for a manifest that declares no `roadmap:` block, so init
  printed `created ... every 300s` and `matches the manifest` about a cadence
  the manifest had never mentioned. The report now names the absence. The
  control beside it is that a manifest which *does* declare a dial is not told
  it declares none.

Scope, stated because the note in US3-S3 is one edit away from being a feature:
this story changes what the reconciliation *reports*, never what it does. The
schedule is still created at the default cadence when none is declared, and
`test_saying_so_does_not_change_what_the_schedule_gets` is the assertion that
holds it there.

No real control plane is reached: `bind_offline_seams` binds the schedule client
to a `FakeScheduleServer`, which is also what every assertion about a live
schedule reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK
from factory.roadmap.schedule import schedule_id_for
from factory.verify.factory_yaml import (
    LEGACY_MANIFEST_NAME,
    MANIFEST_NAME,
    parse_factory_config,
)

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams
from tests.test_ergane_init_wiring import FakeGitHub

#: `make_bare_repo` names the directory `app`, and init normalises the slug out
#: of it, so this is the id every schedule below is stored under.
SLUG = "app"
SCHEDULE = schedule_id_for(SLUG)

#: The cadence `RoadmapDials()` falls back to. Spelled out rather than imported
#: from the dataclass: the point of US3-S3 is that this number reaches the
#: operator's transcript without ever having been declared, and an expectation
#: computed from the code under test could not say so.
DEFAULT_CADENCE = 300

_BASE = """\
version: 2
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: main
"""

#: A manifest that steers its own scheduler: fifteen minutes rather than the
#: five the default would give it.
DECLARES_A_DIAL = _BASE + """\
roadmap:
  cadence_s: 900
"""

#: The same repository with the dial left out — valid, and the state US3-S3 is
#: about.
DECLARES_NO_DIAL = _BASE


def repo_with(tmp_path: Path, manifest: str, *, name: str = MANIFEST_NAME) -> Path:
    """A committed git repository declaring `manifest` under `name`."""
    return make_bare_repo(tmp_path, {"README.md": "# app\n", name: manifest})


def reconcile(
    repo: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer
) -> Any:
    """`ergane init --wire --non-interactive <repo>`, every outward seam bound.

    The non-interactive path, because that is the path US3 names: nobody is
    asked anything, so the manifest is the only thing that can be speaking.
    """
    bind_offline_seams(monkeypatch, FakeGitHub(owner_repo="acme/app"), schedules=floor)
    return _invoke(["init", "--wire", "--non-interactive", str(repo)], monkeypatch)


def schedule_report(stdout: str) -> str:
    """The `schedule:` line init printed, with any lines indented under it.

    The report is what US3 is about, so it is read as init lays it out rather
    than by searching the whole transcript — `ergane init` ends by running the
    check, whose `roadmap_schedule` finding says something similar about the
    same schedule, and a test that matched anywhere in stdout could pass on the
    check's line while init's own said nothing.
    """
    lines = stdout.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("schedule: ")), None
    )
    assert start is not None, f"init printed no schedule line:\n{stdout}"
    report = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith("  "):
            break
        report.append(line)
    return "\n".join(report)


def writes_to(floor: FakeScheduleServer) -> list[tuple[str, str]]:
    """Every call that changed the control plane, describes excluded."""
    return [call for call in floor.calls if call[0] != "describe"]


# ---------------------------------------------------------------------------
# T020 [US3-S1, trap 7] a declared dial the schedule disagrees with is reported
# ---------------------------------------------------------------------------


def test_a_schedule_disagreeing_with_the_declared_dial_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S1: the operator's 900s, against a schedule still running at 300s.

    The report names both numbers and reconciles to the declared one. It is the
    plain case, and it is here because it is the one the finding was written
    about — "it currently prints already satisfied" — so it stays pinned now
    that keeping the manifest has stopped it.
    """
    repo = repo_with(tmp_path, DECLARES_A_DIAL)
    floor = FakeScheduleServer()
    seed(floor, desired_for(repo, slug=SLUG, cadence_s=DEFAULT_CADENCE))

    result = reconcile(repo, monkeypatch, floor)

    assert result.code == EXIT_OK, result.stderr
    report = schedule_report(result.stdout)
    assert "already satisfied" not in report, report
    assert "manifest declares 900" in report, report
    assert [i.every.total_seconds() for i in floor.schedules[SCHEDULE].spec.intervals] == [
        900.0
    ]


def test_a_legacy_named_manifest_is_still_the_manifest_it_reconciles_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S1 where the comparison had no manifest at all — red before US3.

    `factory.yaml` is a name the schema still honours; `resolve_manifest_path`
    is the one helper every reader asks, and `_existing_manifest` asks it, which
    is why US1 keeps this file and init reports the repository joined. The
    reconciliation asked something else — `repo_root / MANIFEST_NAME` — and so
    reported `failed: the manifest just written did not load` about a manifest
    that had not been written and did load, while `--check`, further down the
    same transcript, named the drift correctly.

    The dial is the assertion rather than the absence of the error string: a
    reconciliation that reports the operator's 900s is reading their file.
    """
    repo = repo_with(tmp_path, DECLARES_A_DIAL, name=LEGACY_MANIFEST_NAME)
    floor = FakeScheduleServer()
    seed(floor, desired_for(repo, slug=SLUG, cadence_s=DEFAULT_CADENCE))

    result = reconcile(repo, monkeypatch, floor)

    assert result.code == EXIT_OK, result.stderr
    report = schedule_report(result.stdout)
    assert "did not load" not in report, report
    assert "manifest declares 900" in report, report
    assert [i.every.total_seconds() for i in floor.schedules[SCHEDULE].spec.intervals] == [
        900.0
    ]
    # And the file init kept is the file it reconciled against: no second
    # manifest appeared under the preferred name to make the read succeed.
    assert not (repo / MANIFEST_NAME).exists()


def test_the_dial_is_read_from_the_manifest_init_judged_not_from_disk_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trap 7 at the seam: the comparison's subject is the file, not the write.

    `init_command` loads the manifest once, before anything is written, and that
    object is what decides whether the file is valid and whether it is kept.
    Handing the same object to the reconciliation is what makes "the schedule
    disagrees with your manifest" a statement about the operator's manifest.

    Proven by making the two disagree, which is exactly the situation the
    finding described: the declaration says 900s and the bytes on disk say the
    default. A `_schedule` that re-reads the file reports agreement with its own
    edit — "already satisfied" — which is the sentence US3 exists to remove.
    """
    repo = repo_with(tmp_path, DECLARES_NO_DIAL)
    floor = FakeScheduleServer()
    seed(floor, desired_for(repo, slug=SLUG, cadence_s=DEFAULT_CADENCE))
    bind_offline_seams(monkeypatch, schedules=floor)
    on_disk = init_module._existing_manifest(repo)
    judged = init_module._ExistingManifest(
        path=on_disk.path,
        text=DECLARES_A_DIAL,
        declared=dict(on_disk.declared, roadmap={"cadence_s": 900}),
        config=parse_factory_config(DECLARES_A_DIAL),
    )

    report = init_module._schedule(
        repo, SLUG, control_plane_reason=None, kept=judged
    )

    assert "already satisfied" not in report, report
    assert "manifest declares 900" in report, report


# ---------------------------------------------------------------------------
# T021 [US3-S2] agreement is reported when the two agree
# ---------------------------------------------------------------------------


def test_a_schedule_matching_the_declared_dial_is_reported_as_agreeing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S2, and the control on US3-S1.

    Without this, a reconciliation that shouted "disagrees" at every run would
    satisfy the scenario above. Agreement is asserted twice over: in what the
    operator is told, and on the control plane, which is untouched — a report of
    agreement that had rewritten the schedule to produce it would be the same
    comparing-against-its-own-edit defect one function along.
    """
    repo = repo_with(tmp_path, DECLARES_A_DIAL)
    floor = FakeScheduleServer()
    seed(floor, desired_for(repo, slug=SLUG, cadence_s=900))
    before = floor.snapshot(SCHEDULE)

    result = reconcile(repo, monkeypatch, floor)

    assert result.code == EXIT_OK, result.stderr
    report = schedule_report(result.stdout)
    assert "already satisfied" in report, report
    assert floor.snapshot(SCHEDULE) == before
    assert writes_to(floor) == [], f"a matching schedule was rewritten: {floor.calls}"


# ---------------------------------------------------------------------------
# T022 [US3-S3] a manifest declaring no dial is told so, not told a default
# ---------------------------------------------------------------------------


def test_a_manifest_declaring_no_dial_is_reported_as_declaring_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S3: the absence is named rather than filled in silently.

    Before this story the transcript read `created ergane-roadmap-app —
    created, starting roadmap-specs every 300s`, and 300 is `RoadmapDials()`'s
    fallback: a number the operator never wrote, reported in the position where
    every other number on that line came from their manifest. The report now
    says the manifest declares none, so "every 300s" is readable as a default
    rather than as a declaration.
    """
    repo = repo_with(tmp_path, DECLARES_NO_DIAL)
    floor = FakeScheduleServer()

    result = reconcile(repo, monkeypatch, floor)

    assert result.code == EXIT_OK, result.stderr
    report = schedule_report(result.stdout).lower()
    assert "no roadmap dials" in report, report
    assert "default" in report, report


def test_a_manifest_that_declares_a_dial_is_not_told_it_declares_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control on US3-S3: the note fires on absence and nothing else.

    A note printed on every run is one an operator learns to scroll past, which
    is how the next thing worth reading goes unread.
    """
    repo = repo_with(tmp_path, DECLARES_A_DIAL)
    floor = FakeScheduleServer()

    result = reconcile(repo, monkeypatch, floor)

    assert result.code == EXIT_OK, result.stderr
    assert "no roadmap dials" not in result.stdout.lower(), result.stdout


def test_saying_so_does_not_change_what_the_schedule_gets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3 changes the report, never the reconciliation — the scope assertion.

    The spec is explicit that this is not a reconciliation feature. A repository
    declaring no dial still gets the default cadence and concurrency on its
    schedule, exactly as it did before; what changed is that the operator is
    told where those numbers came from.
    """
    repo = repo_with(tmp_path, DECLARES_NO_DIAL)
    floor = FakeScheduleServer()

    assert reconcile(repo, monkeypatch, floor).code == EXIT_OK

    schedule = floor.schedules[SCHEDULE]
    assert [i.every.total_seconds() for i in schedule.spec.intervals] == [
        float(DEFAULT_CADENCE)
    ]
    assert floor.arguments(SCHEDULE)["max_concurrent_epics"] == 1
    assert floor.arguments(SCHEDULE)["max_concurrent_nodes"] == 1
