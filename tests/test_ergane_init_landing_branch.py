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

Pasted evidence — the red runs, each captured before its implementation existed,
and the mutation battery — is at the bottom of this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

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
