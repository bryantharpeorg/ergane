"""083 US1: `--clean-runtime` says which root it did not clean.

`repo forget --clean-runtime` derives what it deletes from the registry entry
and never from the environment — that is `runtime_root_for`'s whole argument
(`factory/cli/repo.py:400-421`), it is why this repository lost its runtime root
on 2026-08-14, and **this story does not change it**.  What it changes is what
the operator is told when the environment disagrees:

- **The disagreement is disclosed** (FR-002).  `resolve_factory_root()` already
  returns the root, the choice and the variable that supplied it
  (`factory/workgraph/worktree.py:165-170`); nothing here infers anything.  The
  line is in the shape of the legacy-root disclosure eight lines away, because
  the verb already knows how to name a root it did not touch.
- **A run that could not have cleaned anything is refused** (FR-003).  An
  override in force over an entry-derived root with nothing in it prints
  `(0 entries)` and exits 0 today, and an operator cannot tell that from a host
  that is now clean.  The refusal lands before the schedule delete and before
  the entry removal.
- **Neither fires when nothing is wrong** (FR-004).  Two of the five tests here
  are controls, and they are the point: a disclosure that always prints is
  noise, and noise is how the legacy-root line beside it would stop being read.

The two controls are `test_with_no_override_the_output_is_byte_for_byte_todays`
and `test_the_environments_root_is_untouched_and_the_entrys_is_the_one_emptied`.
A third control is not in this file at all and must not move:
`tests/test_ergane_repo_forget.py::test_clean_runtime_empties_the_entrys_root_and_not_the_environments`
already pins the deletion target, and a story that edited the file holding its
own control would be asking which way the green went.

Pasted evidence (constitution VIII / D-037) is at the bottom.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.env import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.roadmap import schedule as roadmap_schedule

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import _invoke
from tests.test_ergane_init_check import bind_offline_seams, make_repo

SLUG = "widgets"


# -----------------------------------------------------------------------------
# Fixtures and helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Every outward seam bound; the control plane the test may inspect."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane)
    return control_plane


@pytest.fixture
def no_epics(monkeypatch: pytest.MonkeyPatch) -> None:
    """The capacity read reports an idle floor.

    Load-bearing in every test here: without it the CLI reaches the operator's
    real Temporal, and a genuinely running epic refuses the verb for a reason
    that has nothing to do with this story (034 evidence, M8).
    """
    import factory.cli.repo as repo_module

    async def empty() -> set[str]:
        return set()

    monkeypatch.setattr(repo_module, "_running_epic_ids", empty)


def registered(tmp_path: Path, *, name: str = "widgets", slug: str = SLUG) -> Path:
    """A scaffolded repo the engine knows about, with an empty `.ergane/`."""
    repo = make_repo(tmp_path, name=name)
    registry.register(slug, repo)
    return repo


def populate(root: Path, *, name: str = "doctor.db") -> Path:
    """One file in a runtime root, so emptying it — or not — is observable.

    A plain file rather than a seeded store: what is under test is which
    directory the deletion walks, and a real SQLite schema would say nothing
    about that while making the failure harder to read.
    """
    root.mkdir(parents=True, exist_ok=True)
    marker = root / name
    marker.write_text("state\n", encoding="utf-8")
    return marker


def decoy_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A populated runtime root the environment points every process at.

    Both variable names are set, as `tests/conftest.py` sets them for the whole
    session: a per-test override of either name has to win cleanly, and setting
    only one would leave the session's own root answering for the other.
    """
    decoy = tmp_path / "host-root"
    populate(decoy, name="host.db")
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(decoy))
    monkeypatch.setenv(FACTORY_ROOT_ENV, str(decoy))
    return decoy


def no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset both root variables the session fixture exports.

    `tests/conftest.py:541-542` points `ERGANE_ROOT` and `FACTORY_ROOT` at a
    session-wide root for every test in the suite, so "no override in force" is
    a state a test has to ask for.  It is also the state an operator is in.
    """
    monkeypatch.delenv(ERGANE_ROOT_ENV, raising=False)
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)


# -----------------------------------------------------------------------------
# T001 / US1-S1, FR-002 — the disagreement is named, and so is the variable
# -----------------------------------------------------------------------------


def test_an_overridden_root_is_named_as_one_it_did_not_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """FR-002: the other root, that an override produced it, and which variable.

    All three come off `resolve_factory_root()`'s existing return triple.  The
    assertions are on stdout, because stdout is what an operator reads when the
    command succeeds — a disagreement whispered to stderr on a run that exits 0
    is the failure mode this story exists to close, one channel over.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    populate(root)
    decoy = decoy_root(tmp_path, monkeypatch)

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert str(decoy) in result.stdout, "the root it did not clean is not named"
    assert "override" in result.stdout, "the disclosure does not say what caused it"
    assert ERGANE_ROOT_ENV in result.stdout, "the variable that supplied it is not named"
    assert f"emptied {root}" in result.stdout, "and the entry-derived root is still the one emptied"


# -----------------------------------------------------------------------------
# T002 / US1-S2, FR-001 — the control: disclosure, never retargeting
# -----------------------------------------------------------------------------


def test_the_environments_root_is_untouched_and_the_entrys_is_the_one_emptied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """**The control.**  The fix is disclosure; the deletion target does not move.

    The filed finding asks for the opposite — empty what `resolve_factory_root()`
    returns — and the finding is wrong (083 plan, trap 1).  An implementer who
    adopted the override would print a perfect disclosure and delete the wrong
    host's state, so the words and the deletion are asserted in the same test:
    the decoy's file survives, its directory is untouched, and the entry-derived
    root is the one that came back empty.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    populate(root)
    (root / "homes").mkdir()
    (root / "homes" / "node.json").write_text("{}", encoding="utf-8")
    decoy = decoy_root(tmp_path, monkeypatch)
    before = sorted(path.name for path in decoy.iterdir())

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert (decoy / "host.db").read_text(encoding="utf-8") == "state\n"
    assert sorted(path.name for path in decoy.iterdir()) == before, "the override was retargeted"
    assert root.is_dir(), "the ignored directory itself belongs to the repo"
    assert list(root.iterdir()) == [], "the entry-derived root was not the one emptied"


# -----------------------------------------------------------------------------
# T003 / US1-S3, FR-003 — the field case: nothing to empty, and it says so
# -----------------------------------------------------------------------------


def test_an_override_over_an_empty_entry_root_is_refused_before_any_act(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """FR-003: `(0 entries)` and exit 0 is output an operator cannot read.

    This is the field case byte for byte — an override in force, an entry-derived
    root with nothing in it — and today it congratulates the operator on a host
    that is still full.  The refusal is taken before the schedule delete and
    before the entry removal (trap 4), so both are asserted still there: a
    half-departure cannot be told from a whole one afterwards.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    assert list(root.iterdir()) == [], "the premise: the entry's root is empty"
    decoy = decoy_root(tmp_path, monkeypatch)

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_USER
    assert str(root) in result.stderr, "the root it would have emptied is not named"
    assert str(decoy) in result.stderr, "the root the environment names is not named"
    assert registry.load_registry().get(SLUG) is not None, "the entry must survive a refusal"
    assert roadmap_schedule.schedule_id_for(SLUG) in floor.schedules, "so must the schedule"
    assert (decoy / "host.db").exists(), "and a refusal deletes nothing anywhere"


# -----------------------------------------------------------------------------
# T004 / US1-S4, FR-004 — the second control: no override, no new line
# -----------------------------------------------------------------------------


def test_with_no_override_the_output_is_byte_for_byte_todays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """**The second control.**  A disclosure that always fires stops being read.

    Asserted as whole-stdout equality rather than as an absence of some phrase,
    because the failure to catch is an *extra line* and no substring assertion
    can name a line nobody has written yet.  The three lines below are what
    `factory/cli/repo.py:376-394` prints today, in their order.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    populate(root)
    no_override(monkeypatch)
    entry_path = registry.load_registry().get(SLUG).path

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert result.stdout == (
        f"deleted roadmap schedule {roadmap_schedule.schedule_id_for(SLUG)}\n"
        f"emptied {root} (1 entry)\n"
        f"forgot {SLUG} ({entry_path}); its own files are untouched\n"
    )


def test_an_empty_root_with_no_override_is_emptied_rather_than_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """FR-003's other edge: an empty root is only suspicious under a disagreement.

    An operator forgetting a repository whose runtime root is already empty —
    cleaned by hand, or never used — has asked for nothing impossible, and
    `(0 entries)` is the truth for them.  A refusal keyed on emptiness alone
    would turn that ordinary departure into an error the operator cannot clear,
    which is why the refusal above takes the disagreement as an argument rather
    than looking at the root by itself.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    assert list(root.iterdir()) == [], "the premise: nothing to empty either way"
    no_override(monkeypatch)

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert f"emptied {root} (0 entries)" in result.stdout
    assert registry.load_registry().get(SLUG) is None, "the departure completed"


# -----------------------------------------------------------------------------
# T005 / US1-S5, FR-004 — two disclosures, neither swallowing the other
# -----------------------------------------------------------------------------


def test_the_legacy_disclosure_and_the_override_disclosure_coexist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """A repo that never migrated keeps its legacy line, and gains the new one.

    Both name a root the verb did not touch and both are written in the same
    voice, so the risk is a diff that replaces one with the other rather than
    adding beside it.  The repo here has both roots populated: `.ergane/` is
    what `runtime_root_for` resolves to, `.factory/` is what it leaves alone,
    and the environment names a third.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    populate(root)
    legacy = repo / ".factory"
    populate(legacy, name="old.db")
    decoy = decoy_root(tmp_path, monkeypatch)

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert f"left {legacy} alone" in result.stdout, "the legacy disclosure was swallowed"
    assert "never migrated" in result.stdout
    assert str(decoy) in result.stdout, "the override disclosure was swallowed"
    assert ERGANE_ROOT_ENV in result.stdout
    assert (legacy / "old.db").exists(), "only the resolved root is emptied"


# -----------------------------------------------------------------------------
# Pasted evidence (constitution VIII / D-037)
#
# Every run below is the real `repo forget` path driven through `main()`, with
# the control plane bound to `FakeScheduleServer` — the same seams every test in
# this file uses.  `/tmp/pytest-of-.../pytest-N/<case>0/` is elided to `.../` and
# nothing else is edited.
#
# The red run, before `factory/cli/repo.py` was touched.  Both controls already
# passed, which is what makes them controls — they describe behaviour that must
# not change, so a control that went red here would have been the wrong test:
#
#   3 failed, 2 passed in 0.44s
#   FAILED ...::test_an_overridden_root_is_named_as_one_it_did_not_clean
#   FAILED ...::test_an_override_over_an_empty_entry_root_is_refused_before_any_act
#   FAILED ...::test_the_legacy_disclosure_and_the_override_disclosure_coexist
#
# SC-001 — a populated decoy at ERGANE_ROOT, a populated entry-derived root:
#
#   $ ergane repo forget widgets --clean-runtime          EXIT=0
#   deleted roadmap schedule ergane-roadmap-widgets
#   emptied .../a/.ergane (1 entry)
#   left .../host-root alone; it is the runtime root the environment override
#   ERGANE_ROOT selects for this host's processes, and only the root derived
#   from the registry entry is emptied
#   forgot widgets (.../a); its own files are untouched
#
#   decoy still holds: ['host.db']        <- named, and not deleted
#   entry root now:    []                 <- the entry-derived one is emptied
#
# SC-002 — the control, both ways.  The same case with no override in force,
# run against the tree before the change and after it.  Byte-identical; the only
# difference is pytest's per-run tmp directory (`pytest-4` vs `pytest-3`), which
# is why the assertion in the test compares against the paths it built:
#
#   BEFORE (HEAD:factory/cli/repo.py)     EXIT=0
#   deleted roadmap schedule ergane-roadmap-widgets
#   emptied .../c/.ergane (1 entry)
#   forgot widgets (.../c); its own files are untouched
#
#   AFTER                                 EXIT=0
#   deleted roadmap schedule ergane-roadmap-widgets
#   emptied .../c/.ergane (1 entry)
#   forgot widgets (.../c); its own files are untouched
#
# SC-003 — the field case: an override in force, an entry-derived root with
# nothing in it.  Today this prints `(0 entries)` and exits 0:
#
#   $ ergane repo forget widgets --clean-runtime          EXIT=1
#   ergane: refusing to empty the runtime root of 'widgets': the entry-derived
#   root .../b/.ergane holds nothing to empty, while ERGANE_ROOT points this
#   host's processes at .../host-root - a different root, which --clean-runtime
#   never deletes.  Emptying 0 entries and exiting 0 here cannot be told from a
#   host that is now clean, and .../host-root would still be full.  Either unset
#   ERGANE_ROOT and re-run, so the root this verb empties and the root your
#   processes use are the same one, or drop --clean-runtime, because
#   .../b/.ergane has nothing in it to clean; nothing was changed
#
#   entry still resolves: True
#   schedules: ['ergane-roadmap-widgets']  <- refused ahead of both acts
#
# US1-S5 — both disclosures, in one run, neither swallowing the other:
#
#   emptied .../d/.ergane (1 entry)
#   left .../host-root alone; it is the runtime root the environment override
#   ERGANE_ROOT selects for [...]
#   left .../d/.factory alone; it is a second runtime root this repo never
#   migrated, and only the resolved one is emptied
#
# Mutation battery — one production behaviour broken at a time, against this
# file plus `tests/test_ergane_repo_forget.py` and `tests/test_repo_ast.py`
# (22 passed at baseline).  A mutation nothing catches is a test that cannot
# fail, so the run is committed rather than summarised:
#
#   M1 the override disclosure is never printed    CAUGHT   2 failed, 20 passed
#   M2 the FR-003 refusal is deleted               CAUGHT   1 failed, 21 passed
#   M3 the deletion adopts the override root       CAUGHT   5 failed, 17 passed
#   M4 the disclosure fires with no override set   CAUGHT   2 failed, 20 passed
#   M5 the refusal ignores whether an override is
#      in force, refusing any empty root           CAUGHT   1 failed, 21 passed
#
# M3 is the one worth reading twice: it is the filed finding's own "fix" — empty
# what `resolve_factory_root()` returns — and it is what this story is a refusal
# of (083 plan, trap 1).  Two of the five tests it fails are in the file this
# story may not edit, and one of them is the 034 control written for exactly
# this mutation:
#
#   FAILED test_clean_runtime_names_the_root_it_did_not_clean.py::
#          test_an_overridden_root_is_named_as_one_it_did_not_clean
#          test_the_environments_root_is_untouched_and_the_entrys_is_the_one_emptied
#          test_an_override_over_an_empty_entry_root_is_refused_before_any_act
#   FAILED test_ergane_repo_forget.py::
#          test_clean_runtime_empties_the_entrys_root_and_not_the_environments
#          test_clean_runtime_is_refused_for_a_root_outside_the_tmp_tree
#
# M4 and M5 are the two controls doing their job: M4 is the disclosure that
# always fires (trap 6, how the legacy line beside it would stop being read),
# M5 is the refusal that fires without a disagreement, which would make an
# ordinary second `forget` of an already-clean repo unclearable.
#
# T006 — the 034 control, run by name, unedited:
#
#   $ uv run pytest -q "tests/test_ergane_repo_forget.py::\
#     test_clean_runtime_empties_the_entrys_root_and_not_the_environments"
#   1 passed in 0.14s
#
# The declared `test` gate over the whole suite, after the change:
#
#   $ uv run pytest -q
#   4256 passed, 52 skipped, 7 warnings in 340.86s (0:05:40)
#
# One thing this evidence cannot show, and it is why `_override_disagreement`
# reads the environment before it calls the resolver: with no override set,
# `resolve_factory_root()`'s last branch *creates* `.ergane/` under the current
# directory (`factory/workgraph/worktree.py:193`).  Calling it unconditionally
# would leave a runtime root in whatever directory the operator ran `forget`
# from — invisible in stdout, and therefore invisible to the FR-004 control
# above, which is the only reason it is written down here instead.
# -----------------------------------------------------------------------------
