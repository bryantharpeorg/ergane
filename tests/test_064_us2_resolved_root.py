"""064/US2: init names the repository it resolved, and asks before enrolling it.

The near-miss this file holds shut: `ergane init` was run from a scratch
directory that happened to sit *beneath* a repository, walked up out of it, and
offered to enrol the parent — twenty-five unrelated projects as one managed
repo. The path was printed, and the reporter happened to read it.

Three properties, and each is easy to fake:

**The prompt has to be required, not merely available.** A test that scripts
`y` and then reads the manifest passes against the unfixed code too, because
the unfixed code never asked and the answer list simply had one entry left
over. So the declining runs assert that *nothing was written* — no manifest, no
`.gitignore`, no runtime root, no registry entry — and the accepting run asserts
the confirmation was `calls[0]`, before the interview began.

**The common case must not acquire a prompt (trap 5).** `test_..._at_the_root_...`
asserts the *exact* prompt sequence, derived from the parser's own key order, so
an extra question anywhere in a root invocation fails rather than passing on a
substring.

**A worktree is not the ambiguity (trap 6).** `resolve_repo_root` already
resolves a linked worktree somewhere else — to the primary checkout — and
refuses, naming it. That refusal must keep arriving with no question asked, so
the worktree tests bind a prompter with no answers at all and assert
`calls == []`: a spurious confirmation there would raise rather than pass.

The red run and the mutation battery are pasted at the bottom of this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.verify.factory_yaml import MANIFEST_NAME, _TOP_LEVEL_KEYS

from tests.target_repo import add_worktree
from tests.test_ergane_init import (
    DEFAULT_ANSWERS,
    Run,
    ScriptedPrompter,
    _git,
    _invoke,
    make_bare_repo,
)
from tests.test_ergane_init_check import bind_offline_seams, make_repo

#: Every question a *root* invocation asks on a repository with no matching
#: stack markers, in the order the parser's own key order puts them — the
#: manifest keys, then the US4 template-source question, then the slug.
#: Derived rather than spelled, so a key added to the schema does not silently
#: license an extra prompt here (034/US6 added `roadmap`; 049/US5 added `forge`).
INTERVIEW_PROMPTS: list[str] = [init_module._PROMPTS[key] for key in _TOP_LEVEL_KEYS] + [
    init_module._TEMPLATE_SOURCE_PROMPT,
    "repo slug",
]

#: "Press enter through every question" — a new list, never an edit of one that
#: already exists (051/SC-004).
PRESS_ENTER: list[str] = [""] * len(INTERVIEW_PROMPTS)


def run_init(
    monkeypatch: pytest.MonkeyPatch,
    *argv: str,
    answers: list[str],
) -> tuple[Run, ScriptedPrompter]:
    """Run `ergane init` with a scripted prompter, returning the run *and* it.

    The prompter comes back because what these tests are about is the question
    the operator was asked — including the case where there must not be one.
    """
    prompter = ScriptedPrompter(list(answers))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    bind_offline_seams(monkeypatch)
    return _invoke(["init", *argv], monkeypatch), prompter


def assert_nothing_written(repo: Path) -> None:
    """No scaffold, and no registry row — the whole point of declining."""
    assert (repo / MANIFEST_NAME).exists() is False
    assert (repo / ".gitignore").exists() is False
    assert (repo / ".ergane").exists() is False
    assert registry.load_registry().for_path(repo) is None


def prompts(prompter: ScriptedPrompter) -> list[str]:
    return [prompt for prompt, _default in prompter.calls]


# --- T011 / US2-S1: a non-repository directory beneath a repository -----------


@pytest.mark.parametrize("declined", ["n", "", "no", "somewhere else"])
def test_a_scratch_directory_under_a_repo_asks_and_declining_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declined: str
) -> None:
    """US2-S1, FR-005: the reporter's invocation, refused rather than assumed.

    The empty answer is in the parameter list on purpose: pressing enter is the
    fastest thing an operator does, and if it enrolled the parent this story
    would have made the near-miss cheaper to hit rather than harder.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    scratch = repo / "scratch" / "not-a-repo"
    scratch.mkdir(parents=True)
    monkeypatch.chdir(scratch)

    result, prompter = run_init(monkeypatch, answers=[declined])

    assert result.code == EXIT_USER
    # It asked, and the question named the repository it resolved.
    assert len(prompter.calls) == 1, prompts(prompter)
    assert str(repo.resolve()) in prompter.calls[0][0]
    # It stated the resolved root where the operator reads output, too.
    assert str(repo.resolve()) in result.stdout + result.stderr
    # And the interview never started: the one question asked was not one of its.
    assert prompter.calls[0][0] not in INTERVIEW_PROMPTS
    assert_nothing_written(repo)


def test_confirming_from_a_scratch_directory_enrols_the_resolved_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of S1: `y` proceeds, and the confirmation came first.

    Without this the story could be "satisfied" by refusing every walk-up, which
    would break the invocation the operator actually meant.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    scratch = repo / "scratch" / "not-a-repo"
    scratch.mkdir(parents=True)
    monkeypatch.chdir(scratch)

    result, prompter = run_init(monkeypatch, answers=["y", *DEFAULT_ANSWERS])

    assert result.code == EXIT_OK
    assert (repo / MANIFEST_NAME).is_file()
    # The confirmation is asked before any interview question, not after eight.
    assert prompts(prompter)[1:] == INTERVIEW_PROMPTS
    assert str(repo.resolve()) in prompter.calls[0][0]


# --- T012 / US2-S2: the common case must not acquire a prompt (trap 5) --------


def test_init_at_the_repository_root_asks_exactly_the_interview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S2, FR-006: the overwhelmingly normal invocation gains no question.

    Asserted as an equality over the whole prompt sequence rather than as "no
    prompt contains 'confirm'": a confirmation phrased any other way would slip
    past a substring check, and operators who learn to press an extra key are
    operators who stop reading the question (trap 5).
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    result, prompter = run_init(monkeypatch, answers=list(DEFAULT_ANSWERS))

    assert result.code == EXIT_OK
    assert (repo / MANIFEST_NAME).is_file()
    assert prompts(prompter) == INTERVIEW_PROMPTS


def test_naming_the_repository_root_explicitly_asks_exactly_the_interview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006 again, by path: `ergane init <root>` from elsewhere is unambiguous.

    The operator named the repository, so there is nothing to confirm — and this
    is the remedy the refusals below tell them to use, which makes it a promise
    rather than a suggestion.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result, prompter = run_init(monkeypatch, str(repo), answers=list(DEFAULT_ANSWERS))

    assert result.code == EXIT_OK
    assert (repo / MANIFEST_NAME).is_file()
    assert prompts(prompter) == INTERVIEW_PROMPTS


# --- T013 / US2-S3: a subdirectory of the repository --------------------------


def test_a_subdirectory_of_the_repository_states_the_root_and_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S3, FR-005: the ambiguous case — plausible, and still named.

    Walking up from `src/` is probably what the operator wanted. Saying so costs
    one keystroke, and the run that declines proves the keystroke is required.
    """
    repo = make_bare_repo(tmp_path, {"src/main.py": "pass\n"})
    subdirectory = repo / "src"
    monkeypatch.chdir(subdirectory)

    declined, declining_prompter = run_init(monkeypatch, answers=["n"])

    assert declined.code == EXIT_USER
    assert len(declining_prompter.calls) == 1
    question = declining_prompter.calls[0][0]
    assert str(repo.resolve()) in question
    assert str(subdirectory.resolve()) in declined.stdout + declined.stderr
    assert_nothing_written(repo)

    accepted, accepting_prompter = run_init(
        monkeypatch, answers=["y", *DEFAULT_ANSWERS]
    )

    assert accepted.code == EXIT_OK
    assert (repo / MANIFEST_NAME).is_file()
    assert prompts(accepting_prompter)[1:] == INTERVIEW_PROMPTS


# --- T014 / US2-S4: `--non-interactive` refuses rather than assuming ----------


def test_non_interactive_refuses_a_resolved_root_it_cannot_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S4, FR-007: an absent answer is not an answer (060's rule, again).

    The paired run is what makes this a statement about the *root*, not about
    the flag: naming the repository explicitly under the same flag completes, so
    the refusal cannot be satisfied by breaking `--non-interactive`.
    """
    repo = make_bare_repo(tmp_path, {"src/main.py": "pass\n"})
    subdirectory = repo / "src"
    monkeypatch.chdir(subdirectory)

    refused, prompter = run_init(monkeypatch, "--non-interactive", answers=[])

    assert refused.code == EXIT_USER
    assert prompter.calls == []
    assert str(repo.resolve()) in refused.stderr
    assert str(subdirectory.resolve()) in refused.stderr
    assert "--non-interactive" in refused.stderr
    assert_nothing_written(repo)

    named, _ = run_init(monkeypatch, "--non-interactive", str(repo), answers=[])

    assert named.code == EXIT_OK
    assert (repo / MANIFEST_NAME).is_file()


# --- T015 / US2-S5: `--check` reports the resolved root as a finding ----------


def finding_lines(stdout: str) -> list[str]:
    """The report's finding lines — never its header, which is the whole point."""
    return [line for line in stdout.splitlines() if line.strip().startswith("[")]


def test_check_reports_the_resolved_root_as_a_finding_not_only_a_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S5, FR-008: the surface an operator is looking at.

    The reporter caught the near-miss from a header line they happened to read.
    So the assertion is deliberately made against the finding lines with the
    header excluded: a fix that only improved the header passes the obvious test
    and fails this one.
    """
    repo = make_repo(tmp_path)
    subdirectory = repo / "src"
    subdirectory.mkdir()
    registry.register("widgets", repo)
    bind_offline_seams(monkeypatch)
    monkeypatch.chdir(subdirectory)

    result = _invoke(["init", "--check"], monkeypatch)

    assert result.code == EXIT_OK, result.stdout
    reported = finding_lines(result.stdout)
    assert reported, "the run must have rendered a report at all"
    root_findings = [line for line in reported if str(repo.resolve()) in line]
    assert root_findings, f"the resolved root appears only in the header: {result.stdout}"
    assert any(str(subdirectory.resolve()) in line for line in root_findings)
    assert any("resolved_root" in line for line in reported)

    # The finding is a finding, not a rendering trick: it is in the profile the
    # judgment returned, and it names both directories there too.
    profile = init_module.check_repo(repo, invocation_dir=subdirectory)
    detail = {f.check: f.detail for f in profile.findings}["resolved_root"]
    assert str(repo.resolve()) in detail
    assert str(subdirectory.resolve()) in detail
    assert profile.passed is True


def test_check_at_the_root_still_names_the_repository_in_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-008 holds unconditionally: the finding is present at the root as well.

    A finding that only appeared in the ambiguous case would be one an operator
    never learns to look for.
    """
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    bind_offline_seams(monkeypatch)
    monkeypatch.chdir(repo)

    result = _invoke(["init", "--check"], monkeypatch)

    assert result.code == EXIT_OK, result.stdout
    named = [
        line
        for line in finding_lines(result.stdout)
        if "resolved_root" in line and str(repo.resolve()) in line
    ]
    assert named, result.stdout


# --- T016 / Edge cases: a worktree, and a repository with no commits ----------


def test_a_linked_worktree_is_refused_with_no_question_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trap 6: a worktree resolves elsewhere legitimately, and is not the ambiguity.

    `resolve_repo_root` names the primary checkout as the parent of
    `--git-common-dir` and refuses. That is correct behaviour and must not turn
    into a confirmation — the prompter here holds no answers at all, so a
    spurious question raises instead of quietly passing.
    """
    primary = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    worktree = tmp_path / "wt"
    add_worktree(primary, worktree)

    at_root, root_prompter = run_init(monkeypatch, str(worktree), answers=[])

    assert at_root.code == EXIT_USER
    assert "worktree" in at_root.stderr.lower()
    assert str(primary.resolve()) in at_root.stderr
    assert root_prompter.calls == []

    # The dangerous shape: a walk-up *inside* a worktree. Still the worktree
    # refusal, still no question.
    nested = worktree / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)

    inside, nested_prompter = run_init(monkeypatch, answers=[])

    assert inside.code == EXIT_USER
    assert "worktree" in inside.stderr.lower()
    assert nested_prompter.calls == []
    assert (worktree / MANIFEST_NAME).exists() is False
    assert (primary / MANIFEST_NAME).exists() is False


def test_a_repository_with_no_commits_still_behaves_as_051_established(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare `git init` root: no confirmation, and 051's offered literal intact.

    An empty repository has no resolvable HEAD, which is exactly the state that
    tempts a resolver into treating "could not read the repository" as "resolved
    somewhere else". It is the root; there is nothing to confirm.
    """
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-b", "master", "--quiet")
    monkeypatch.chdir(repo)

    result, prompter = run_init(monkeypatch, answers=list(PRESS_ENTER))

    assert result.code == EXIT_OK
    assert prompts(prompter) == INTERVIEW_PROMPTS
    # 051/US1-S3: no resolvable HEAD means the literal, not an invented branch.
    assert (init_module._PROMPTS["landing_branch"], "main") in prompter.calls


# -----------------------------------------------------------------------------
# Pasted evidence
# -----------------------------------------------------------------------------
#
# THE RED RUN, captured against this file before any of 064/US2 existed —
# `uv run pytest tests/test_064_us2_resolved_root.py -q`:
#
#     FAILED test_a_scratch_directory_under_a_repo_asks_and_declining_writes_nothing[n]
#     FAILED test_a_scratch_directory_under_a_repo_asks_and_declining_writes_nothing[]
#     FAILED test_a_scratch_directory_under_a_repo_asks_and_declining_writes_nothing[no]
#     FAILED test_a_scratch_directory_under_a_repo_asks_and_declining_writes_nothing[somewhere else]
#     FAILED test_confirming_from_a_scratch_directory_enrols_the_resolved_root
#     FAILED test_a_subdirectory_of_the_repository_states_the_root_and_asks
#     FAILED test_non_interactive_refuses_a_resolved_root_it_cannot_confirm
#     FAILED test_check_reports_the_resolved_root_as_a_finding_not_only_a_header
#     FAILED test_check_at_the_root_still_names_the_repository_in_a_finding
#     9 failed, 4 passed in 0.48s
#
# The four that were already green are the ones that must be green either side:
# the two root invocations, the worktree refusal and the empty repository. They
# are regression guards, and a story that made any of them fail would have
# bought scenario 1 by breaking scenario 2.
#
# THE MUTATION BATTERY. Each mutation was applied to the shipped implementation
# on its own, the file re-run, and the mutation reverted:
#
#   M1  never ask (the pre-064 behaviour, restored)   7 failed, 6 passed
#       FAILED ...declining_writes_nothing[n] [] [no] [somewhere else]
#       FAILED test_confirming_from_a_scratch_directory_enrols_the_resolved_root
#       FAILED test_a_subdirectory_of_the_repository_states_the_root_and_asks
#       FAILED test_non_interactive_refuses_a_resolved_root_it_cannot_confirm
#
#   M2  every answer is consent                       5 failed, 8 passed
#       FAILED ...declining_writes_nothing[n] [] [no] [somewhere else]
#       FAILED test_a_subdirectory_of_the_repository_states_the_root_and_asks
#
#   M3  ask always, root included (trap 5)            4 failed, 9 passed
#       FAILED test_init_at_the_repository_root_asks_exactly_the_interview
#       FAILED test_naming_the_repository_root_explicitly_asks_exactly_the_interview
#       FAILED test_non_interactive_refuses_a_resolved_root_it_cannot_confirm
#       FAILED test_a_repository_with_no_commits_still_behaves_as_051_established
#
#   M4  --non-interactive assumes consent (trap 7)    1 failed, 12 passed
#       FAILED test_non_interactive_refuses_a_resolved_root_it_cannot_confirm
#
#   M5  the root is in the header only, no finding    2 failed, 11 passed
#       FAILED test_check_reports_the_resolved_root_as_a_finding_not_only_a_header
#       FAILED test_check_at_the_root_still_names_the_repository_in_a_finding
#
#   M6  a linked worktree stops being refused, so it  1 failed, 12 passed
#       reaches the walk-up comparison (trap 6)
#       FAILED test_a_linked_worktree_is_refused_with_no_question_asked
#
# With every mutation reverted: 13 passed.
#
# M3 is the one worth reading twice. It is the *tempting* implementation —
# always name the root, always ask — and four tests kill it, three of them the
# ordinary invocations this command exists to serve.
#
# THE MACHINE TRANSCRIPT — the shipped `ergane` binary, run the way the reporter
# ran it: `mkdir -p /tmp/us2-demo/app/scratch/not-a-repo`, `git init` at `app`,
# then from the scratch directory. Unit tests drive the CLI in-process, so this
# is the half they cannot claim.
#
#     $ echo n | ergane init
#     init resolved the repository root to /tmp/us2-demo/app, walking up from /tmp/us2-demo/app/scratch/not-a-repo
#     /tmp/us2-demo/app/scratch/not-a-repo is not a repository root — enrol /tmp/us2-demo/app instead? (y/N) [n]:
#     ergane: declined: /tmp/us2-demo/app was not enrolled and nothing was written — run `ergane init /tmp/us2-demo/app` to enrol it, or run init from the repository you meant
#     exit=1
#     $ ls -a /tmp/us2-demo/app
#     . .. .git README.md scratch          <- no ergane.yaml, no .gitignore, no .ergane
#
#     $ ergane init --non-interactive
#     ergane: init resolved the repository root to /tmp/us2-demo/app, which is not the directory it was invoked from (/tmp/us2-demo/app/scratch/not-a-repo); --non-interactive has nobody to ask, and an absent answer is not consent — run `ergane init /tmp/us2-demo/app` to name the repository you mean, or re-run without --non-interactive to confirm it
#     exit=1
#     $ ls -a /tmp/us2-demo/app
#     . .. .git README.md scratch
#
#     $ ergane init --check          (ERGANE_CONFIG_PATH pointed at a path that
#                                     does not exist, so no probe is delivered)
#     ergane readiness for /tmp/us2-demo/app (ergane.yaml)
#       [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): ...
#       [FAIL] factory_yaml: manifest failed to load: ...
#       [PASS] resolved_root: this report is about /tmp/us2-demo/app, resolved by walking up from /tmp/us2-demo/app/scratch/not-a-repo, which is not a repository root — run `ergane init /tmp/us2-demo/app` to name it outright
#       [FAIL] runtime_root_ignored: ...
#       [FAIL] registry_entry: ...
#       [FAIL] landing_branch: ...
#       [FAIL] control_plane: ...
#       [FAIL] roadmap_schedule: ...
#     7 of 8 checks failed
#     exit=1
#
# The last one is FR-008 at the terminal: the resolved root is a finding line,
# in the list an operator is already scanning, and it renders in a report that
# is otherwise failing — no other finding masks it and it masks none of them.
