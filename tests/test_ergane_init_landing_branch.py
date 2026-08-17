"""051/US1: the landing-branch question offers the branch the repository is on.

`git init` on a stock machine creates `master`; the interview offered the
literal `main`; and the readiness check then failed on a fact the tool already
had in hand when it asked. These tests hold the *offer*, not the answer.

Two things about this file are deliberate and easy to undo by accident.

**The fixtures create `master`, explicitly.** `git init -b master`, not whatever
`init.defaultBranch` this host sets. On a machine configured with
`init.defaultBranch = main` — this project's boxes, and most developer machines
configured after 2020 — the derived branch and the old literal *coincide*, and
every assertion below passes against the unfixed code. A fixture that inherits
the host's default is a fixture that cannot fail on the author's laptop.

**The assertions read `prompter.calls`, which records what the operator was
offered.** A test that scripts the answer `master` and then reads the manifest
passes against the unfixed code too, because the operator's answer was always
honoured. The defect is in what the question *says* before anyone types, so the
offered default is what is asserted (plan trap 3).

Pasted evidence — the red runs, each captured before its implementation existed
— is at the bottom of this file. The full suite, the mutation battery and the
SC-001 machine transcript live beside the spec, in
`specs/051-first-run-defaults/evidence/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK
from factory.mergequeue import onboard
from factory.mergequeue.models import Finding
from factory.verify.factory_yaml import _TOP_LEVEL_KEYS

from tests.test_ergane_init import Run, ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams

#: One blank answer per question: the eight manifest keys, then the slug. This
#: is "press enter through the interview" — the shortest possible first run, and
#: the run the spec's Context transcript came from. A *new* list in a *new*
#: file: SC-004 forbids editing any scripted answer list that already exists.
PRESS_ENTER: list[str] = [""] * (len(_TOP_LEVEL_KEYS) + 1)


def make_master_repo(tmp_path: Path, *, name: str = "app", commit: bool = True) -> Path:
    """A repository whose current branch is `master`, as stock git creates it.

    `-b master` is passed explicitly rather than left to `init.defaultBranch`:
    see the module docstring. `commit=False` leaves the repository empty — no
    commits, no resolvable HEAD — which is scenario 3's subject.
    """
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "master", "--quiet")
    if commit:
        (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def run_init(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    answers: list[str] | None = None,
) -> tuple[Run, ScriptedPrompter]:
    """Run `ergane init` in `repo` with a scripted prompter, returning both.

    The prompter comes back so a test can read `calls` — the record of what the
    operator was *offered*, which is what these tests are about.
    """
    prompter = ScriptedPrompter(list(PRESS_ENTER if answers is None else answers))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    bind_offline_seams(monkeypatch)
    monkeypatch.chdir(repo)
    return _invoke(["init"], monkeypatch), prompter


def offered(prompter: ScriptedPrompter, prompt: str) -> str | None:
    """The default offered for one question, or None when it was never asked."""
    for asked, default in prompter.calls:
        if asked == prompt:
            return default
    return None


LANDING_BRANCH_PROMPT = init_module._PROMPTS["landing_branch"]


# --- T001 / US1-S1: what the question says before the operator types ----------


def test_the_question_offers_the_branch_the_repository_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S1, FR-001: on a `master` repository the offered default is `master`.

    Asserted against the prompt's offered default, never against the accepted
    value: scripting the answer would pass against the unfixed code (trap 3).
    """
    repo = make_master_repo(tmp_path)

    result, prompter = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK
    assert offered(prompter, LANDING_BRANCH_PROMPT) == "master"
    assert (LANDING_BRANCH_PROMPT, "main") not in prompter.calls


# --- T002 / US1-S2: the real check, against the real written file -------------


def landing_branch_finding(repo: Path) -> Finding:
    """Run the shipped readiness check over the manifest `init` just wrote.

    Deliberately not a constructed `InitFacts`: the facts are gathered from the
    repository on disk by the same function `ergane init --check` calls, and the
    judgment is `onboard._landing_branch_finding` itself. A test that built its
    own profile would prove the check agrees with the test, not with the file.
    """
    facts = init_module.gather_init_facts(repo)
    findings: list[Finding] = []
    onboard._landing_branch_finding(findings, facts)
    assert len(findings) == 1, findings
    return findings[0]


def test_pressing_enter_writes_master_and_the_real_check_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S2, FR-001: enter through the interview, and the check passes.

    This is SC-001's claim reduced to a unit: the manifest the operator did not
    have to think about declares the branch they are actually on, and the check
    that failed in the spec's Context transcript now passes.
    """
    repo = make_master_repo(tmp_path)

    result, _prompter = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK
    written = yaml.safe_load((repo / "ergane.yaml").read_text(encoding="utf-8"))
    assert written["landing_branch"] == "master"

    finding = landing_branch_finding(repo)
    assert finding.passed, finding.detail
    assert "master" in finding.detail

    # And the report the operator reads at the end of `ergane init` says so.
    assert "[PASS] landing_branch" in result.stdout


# --- T003 / US1-S3: an empty repository is not an error -----------------------


def test_the_branch_reading_answers_none_when_head_does_not_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-002: the reading distinguishes three HEAD states, and only one is a branch.

    The route choice the plan left open, settled by measurement rather than by
    preference. Against git 2.43 the two candidate readings disagree:

        state                     symbolic-ref --short HEAD   rev-parse --abbrev-ref HEAD
        on `master`, committed    master              rc 0    master              rc 0
        empty, no commit          master              rc 0    (fatal)             rc 128
        detached HEAD             (fatal)             rc 128  HEAD                rc 0

    `rev-parse` is the one whose failure *is* FR-002's "no resolvable HEAD", so
    it is the one used — with the detached-HEAD answer `HEAD` rejected, because
    git refuses to create a branch by that name and so it can only be the
    sentinel. `symbolic-ref` would name the unborn branch of an empty
    repository, which scenario 3 says must not be offered.
    """
    committed = make_master_repo(tmp_path, name="committed")
    empty = make_master_repo(tmp_path, name="empty", commit=False)

    assert init_module._current_branch(committed) == "master"
    assert init_module._current_branch(empty) is None

    _git(committed, "checkout", "--quiet", "--detach", "HEAD")
    assert init_module._current_branch(committed) is None


def test_an_empty_repository_offers_the_literal_and_init_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S3, FR-002: no commits, no resolvable HEAD — the literal, not a failure.

    Joining a repository before its first commit is a normal thing to do, so
    this must not raise and must not invent a branch. It also carries FR-005:
    the report still says `[FAIL] landing_branch`, because an empty repository
    has no refs at all and *no* offered value could pass there. The offer is an
    offer; the readiness check stays the verdict.

    Green before the implementation as well as after — it is the assertion that
    makes the *wrong* reading fail. The mutation battery at the bottom of this
    file shows it going red under `symbolic-ref`, which would offer `master`
    here.
    """
    repo = make_master_repo(tmp_path, commit=False)

    result, prompter = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK
    # Twice over, on purpose. By reference, because "the existing literal" is a
    # structural claim about *which* value is the fallback; and by name, because
    # a test that only spelled the constant would follow a mutation of it and
    # never go red.
    assert offered(prompter, LANDING_BRANCH_PROMPT) == (
        init_module._PLACEHOLDERS["landing_branch"]
    )
    assert offered(prompter, LANDING_BRANCH_PROMPT) == "main"
    written = yaml.safe_load((repo / "ergane.yaml").read_text(encoding="utf-8"))
    assert written["landing_branch"] == "main"
    assert "[FAIL] landing_branch" in result.stdout


# --- T004 / US1-S4: a default, not a constraint -------------------------------


def answering(landing_branch: str) -> list[str]:
    """`PRESS_ENTER` with one question answered — located by key, not by index.

    `_TOP_LEVEL_KEYS.index` rather than a hardcoded `5`: the interview is
    generated from that tuple, and a list that counted positions by hand would
    answer the wrong question the day the schema grows one.
    """
    answers = list(PRESS_ENTER)
    answers[_TOP_LEVEL_KEYS.index("landing_branch")] = landing_branch
    return answers


def test_a_typed_branch_wins_unchanged_over_the_derived_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S4, FR-003: the operator types `release`, and `release` is written.

    Both halves matter. The offer is still the repository's branch — so this is
    a genuine override of a derived value, not of the old literal — and the
    typed answer survives it unchanged.
    """
    repo = make_master_repo(tmp_path)
    _git(repo, "branch", "release")

    result, prompter = run_init(repo, monkeypatch, answers=answering("release"))

    assert result.code == EXIT_OK
    assert offered(prompter, LANDING_BRANCH_PROMPT) == "master"
    written = yaml.safe_load((repo / "ergane.yaml").read_text(encoding="utf-8"))
    assert written["landing_branch"] == "release"

    # The typed branch is what the check then judges, not the derived one.
    finding = landing_branch_finding(repo)
    assert finding.passed, finding.detail
    assert "release" in finding.detail


# --- T005 / US1-S5: a joined repository reconciles, it does not re-point -------


EXISTING_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: uv run pytest -q
landing_branch: main
"""


def test_an_existing_manifest_is_offered_ahead_of_the_repository_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S5, FR-004: what is declared beats what is checked out.

    This behaviour already exists — `_build_defaults` prefers the existing
    manifest's value over the placeholder — so this test pins it rather than
    building it. It is here because the derivation goes *underneath* that
    preference, and a diff that put it in front would silently re-point a joined
    repository at whatever branch happened to be checked out.

    The repository is on `master` and the manifest declares `main`, so the two
    answers differ: a diff that dropped the preference would offer `master` and
    fail here. On a repository whose branch already matched its manifest the two
    coincide and this test could not fail at all.
    """
    repo = make_master_repo(tmp_path)
    (repo / "ergane.yaml").write_text(EXISTING_MANIFEST, encoding="utf-8")

    result, prompter = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK
    assert offered(prompter, LANDING_BRANCH_PROMPT) == "main"
    written = yaml.safe_load((repo / "ergane.yaml").read_text(encoding="utf-8"))
    assert written["landing_branch"] == "main"


# --- T007 / FR-005: an offer, and the check is still the verdict --------------


def test_the_derived_branch_rides_the_default_slot_every_question_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-005: the reading is offered, never announced as verified.

    The question's *text* is unchanged and claims nothing — no "detected", no
    "verified". The branch arrives in the `default=` slot that carries every
    other answer the interview proposes, which is the slot the operator already
    knows they can type over. Nothing here re-implements the verdict:
    `onboard._landing_branch_finding` is the only thing that says whether the
    branch exists, and this story does not touch it.

    SC-004 rides along: the interview asks one question per manifest key plus
    the slug, and no more. A story that added a key would break the nine
    scripted interviews already in this suite (FR-010).
    """
    repo = make_master_repo(tmp_path)

    _result, prompter = run_init(repo, monkeypatch)

    assert LANDING_BRANCH_PROMPT == "landing branch"
    assert (LANDING_BRANCH_PROMPT, "master") in prompter.calls
    assert len(prompter.calls) == len(_TOP_LEVEL_KEYS) + 1


# --- Pasted evidence: the red runs, before any implementation existed ---------
#
# T001, against the tree at 3e9cbde. The fixture repository is on `master` and
# the interview offered the literal:
#
#     >       assert offered(prompter, LANDING_BRANCH_PROMPT) == "master"
#     E       AssertionError: assert 'main' == 'master'
#     E         - master
#     E         + main
#     1 failed in 0.17s
#
# T002, same tree — the manifest an operator who pressed enter would have got:
#
#     >       assert written["landing_branch"] == "master"
#     E       AssertionError: assert 'main' == 'master'
#     2 failed in 0.20s
#
# T003, the reading itself. The seam did not exist:
#
#     >       assert init_module._current_branch(committed) == "master"
#     E       AttributeError: module 'factory.cli.init' has no attribute
#     E                       '_current_branch'
#     3 failed, 1 passed in 0.22s
#
# T004 / T005 / T007 together:
#
#     >       assert (LANDING_BRANCH_PROMPT, "master") in prompter.calls
#     E       assert ('landing branch', 'master') in [('schema version', '1'),
#     E         ('runtime backend', 'bwrap'), ..., ('landing branch', 'main'), ...]
#     5 failed, 2 passed in 0.29s
#
# Two of the seven were green from the start and are declared as such in their
# own docstrings, because a test that pins existing behaviour is worth having
# and worth labelling: `test_an_existing_manifest_is_offered_ahead_of_the_
# repository_reading` (FR-004 was already built; the brief said to pin it) and
# `test_an_empty_repository_offers_the_literal_and_init_completes` (FR-002's
# behaviour was already correct). Both are what make a *wrong* implementation
# fail — mutants M2, M4 and M5 in
# `specs/051-first-run-defaults/evidence/us1-mutations.md` are exactly those two
# going red.
#
# After the implementation, on this file alone:
#
#     7 passed in 0.29s
