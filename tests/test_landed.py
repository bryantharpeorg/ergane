"""Landed facts and fingerprints: per-story baseline from default-branch history.

The reader is the pure seam US2's delta function builds on: it turns git + the
corpus into a map of story key → landing commit, with provenance distinguishing
attested baselines from observed attributions. It also pins each landed story's
fingerprint — its judgeable criteria and work-graph declaration — at any
revision, so drift detection compares the spec as it stands to the spec as it
was when the story landed, never to the working tree.

Fixtures are real git repositories built per test from a tiny spec skeleton.
Commit dates and identity are fixed so hashes are reproducible across machines;
the helpers live beside the tests rather than in a shared fixture module because
the shape of the spec and the commits are the test's own evidence.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.workgraph.landed import (
    Fingerprint,
    LandedFact,
    LandedKind,
    WorktreeError,
    fingerprint,
    landed_facts,
)

DEFAULT_BRANCH = "main"

#: Fixture identity and timestamps are fixed so commit hashes are reproducible.
_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _git_env(home: Path) -> dict[str, str]:
    """A git environment that ignores the host operator's configuration."""
    name, email = _FIXTURE_IDENTITY
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": _FIXTURE_TIMESTAMP,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": _FIXTURE_TIMESTAMP,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    """Run one git command in `repo`, returning stdout; raise on failure."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed.stdout


def _commit(
    repo: Path,
    subject: str,
    *,
    env: dict[str, str],
    body: str = "",
    allow_empty: bool = False,
) -> str:
    """Commit and return the full sha of the new commit."""
    message = subject if not body else f"{subject}\n\n{body}"
    args = ["commit", "--quiet", "-m", message]
    if allow_empty:
        args.append("--allow-empty")
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


@pytest.fixture
def repo_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Factory that builds a fresh git repo with one or more spec files."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    def build(specs: dict[str, str], *, default_branch: str = DEFAULT_BRANCH) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        env = _git_env(empty_home)
        # Do not borrow any host identity either.
        for key in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        ):
            monkeypatch.delenv(key, raising=False)
        _git(repo, "init", "-b", default_branch, "--quiet", env=env)
        specs_dir = repo / "specs" / "016-delta-derivation"
        specs_dir.mkdir(parents=True)
        for name, text in specs.items():
            (specs_dir / name).write_text(text, encoding="utf-8")
        _git(repo, "add", "-A", env=env)
        # Initial commit with content; tests add their own follow-up commits.
        _commit(repo, "fixture skeleton", env=env)
        return repo

    return build


def _spec(
    *, state: str | None = None,
    stories: list[str] | None = None,
    work_graph: str = "",
) -> str:
    """A minimal Spec Kit feature spec with the requested pieces."""
    front = "---\n"
    if state is not None:
        front += f"state: {state}\n"
    front += "---\n"
    body = "# Feature\n\n"
    if stories:
        body += "## Requirements *(mandatory)*\n\n- **FR-001**: The system MUST do one thing.\n\n"
    stories = stories or []
    for number, title in enumerate(stories, start=1):
        body += (
            f"### User Story {number} - {title} (Priority: P{number})\n\n"
            "As the operator, I want this.\n\n"
            "**Acceptance Scenarios**:\n"
            f"1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        )
    if work_graph:
        body += "## Work Graph\n\n```yaml\n" + work_graph + "\n```\n"
    return front + body


# --- T003: landed-facts grammar ----------------------------------------------


def test_attributed_commit_yields_landed_fact(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    sha = _commit(
        repo,
        "016-delta-derivation/us1: US1 (#1)",
        env=env,
        allow_empty=True,
    )
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {"US1": LandedFact(story_key="US1", commit=sha, kind=LandedKind.OBSERVED)}


def test_unattributed_subjects_contribute_nothing(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "docs: fix a typo", env=env, allow_empty=True)
    _commit(repo, "operator note: not a landing", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {}


def test_relanded_story_reports_newest_commit(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    second = _commit(repo, "016-delta-derivation/us1: US1 (#2)", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {"US1": LandedFact(story_key="US1", commit=second, kind=LandedKind.OBSERVED)}
    assert first not in {fact.commit for fact in facts.values()}


def test_story_without_attribution_reports_unlanded(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1", "US2"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    sha = _commit(repo, "016-delta-derivation/us2: US2 (#1)", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {
        "US2": LandedFact(story_key="US2", commit=sha, kind=LandedKind.OBSERVED),
    }


def test_subject_must_match_epic_anchor(repo_builder: Callable[..., Path]) -> None:
    """A subject carrying another epic's attribution is invisible to this reader."""
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "999-other/us1: US1 (#1)", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {}


# --- T004: attestation fallback per story, not per spec ----------------------


def test_attested_landed_without_attribution_baselines_every_story(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(state="draft", stories=["US1", "US2"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    # First commit is just the draft skeleton, not an attestation.
    _commit(repo, "fixture skeleton", env=env, allow_empty=True)
    # Now introduce the attestation in its own commit.
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(
        _spec(state="landed", stories=["US1", "US2"]), encoding="utf-8"
    )
    _git(repo, "add", "-A", env=env)
    sha = _commit(repo, "attest landed", env=env)
    # Add an empty commit so HEAD has a parent; the attesting commit must still
    # be the one that introduced the frontmatter attestation, not HEAD.
    _commit(repo, "operator edit after attestation", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {
        "US1": LandedFact(story_key="US1", commit=sha, kind=LandedKind.ATTESTED),
        "US2": LandedFact(story_key="US2", commit=sha, kind=LandedKind.ATTESTED),
    }


def test_unattested_unattributed_spec_yields_empty_baseline(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {}


def _attest_in_followup(repo: Path, env: dict[str, str]) -> str:
    """Write `state: landed` into the spec and commit it, returning the sha."""
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(
        _spec(state="landed", stories=["US1", "US2"]), encoding="utf-8"
    )
    _git(repo, "add", "-A", env=env)
    return _commit(repo, "attest landed", env=env)


def test_mixed_attested_and_attributed_resolves_per_story(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(state="draft", stories=["US1", "US2"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "fixture skeleton", env=env, allow_empty=True)
    attesting = _attest_in_followup(repo, env)
    attributed = _commit(repo, "016-delta-derivation/us2: US2 (#1)", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {
        "US1": LandedFact(story_key="US1", commit=attesting, kind=LandedKind.ATTESTED),
        "US2": LandedFact(story_key="US2", commit=attributed, kind=LandedKind.OBSERVED),
    }


def test_attribution_beats_attestation_for_a_story(repo_builder: Callable[..., Path]) -> None:
    """The attesting commit is older than the attributed landing: the attributed
    one wins for US2, while a sibling with no attribution still falls back."""
    repo = repo_builder({"spec.md": _spec(state="draft", stories=["US1", "US2"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, "fixture skeleton", env=env, allow_empty=True)
    attesting = _attest_in_followup(repo, env)
    _commit(repo, "operator edit after attestation", env=env, allow_empty=True)
    attributed = _commit(repo, "016-delta-derivation/us2: US2 (#1)", env=env, allow_empty=True)
    facts = landed_facts(repo, "016-delta-derivation", default_branch=DEFAULT_BRANCH)
    assert facts == {
        "US1": LandedFact(story_key="US1", commit=attesting, kind=LandedKind.ATTESTED),
        "US2": LandedFact(story_key="US2", commit=attributed, kind=LandedKind.OBSERVED),
    }


# --- T005: fingerprints --------------------------------------------------------


def test_fingerprint_at_revision_matches_that_revision(repo_builder: Callable[..., Path]) -> None:
    spec = _spec(
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: []\n",
    )
    repo = repo_builder({"spec.md": spec})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)

    # Edit the working tree without committing.
    spec_path = repo / "specs" / "016-delta-derivation" / "spec.md"
    spec_path.write_text(spec + "\n<!-- working-tree edit -->\n", encoding="utf-8")

    fp = fingerprint(repo, first, "016-delta-derivation", "US1")
    assert fp.revision == first
    # The pinned fingerprint must not see the working-tree edit.
    assert "working-tree edit" not in str(fp)


def test_fingerprint_changes_with_scenario_edit(repo_builder: Callable[..., Path]) -> None:
    base = _spec(stories=["US1"], work_graph="US1:\n  depends_on: []\n  implements: []\n")
    repo = repo_builder({"spec.md": base})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    changed = base.replace("**Then** it works", "**Then** it works differently")
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(changed, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    second = _commit(repo, "016-delta-derivation/us1: US1 (#2)", env=env)

    fp1 = fingerprint(repo, first, "016-delta-derivation", "US1")
    fp2 = fingerprint(repo, second, "016-delta-derivation", "US1")
    assert fp1.digest != fp2.digest


def test_fingerprint_changes_with_fr_body_edit(repo_builder: Callable[..., Path]) -> None:
    # _spec already declares FR-001 once; edit that existing body.
    base = _spec(stories=["US1"], work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n")
    repo = repo_builder({"spec.md": base})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    changed = base.replace("MUST do one thing", "MUST do another thing")
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(changed, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    second = _commit(repo, "016-delta-derivation/us1: US1 (#2)", env=env)

    fp1 = fingerprint(repo, first, "016-delta-derivation", "US1")
    fp2 = fingerprint(repo, second, "016-delta-derivation", "US1")
    assert fp1.digest != fp2.digest


def test_fingerprint_changes_with_declaration_edit(repo_builder: Callable[..., Path]) -> None:
    base = _spec(stories=["US1", "US2"], work_graph="US1:\n  depends_on: []\n  implements: []\n")
    repo = repo_builder({"spec.md": base})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    changed = base.replace(
        "US1:\n  depends_on: []\n  implements: []\n",
        "US1:\n  depends_on: [US2]\n  implements: []\n",
    )
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(changed, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    second = _commit(repo, "016-delta-derivation/us1: US1 (#2)", env=env)

    fp1 = fingerprint(repo, first, "016-delta-derivation", "US1")
    fp2 = fingerprint(repo, second, "016-delta-derivation", "US1")
    assert fp1.digest != fp2.digest


def test_fingerprint_unchanged_by_whitespace_reflow(repo_builder: Callable[..., Path]) -> None:
    base = _spec(stories=["US1"], work_graph="US1:\n  depends_on: []\n  implements: []\n")
    repo = repo_builder({"spec.md": base})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    first = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    # Extra spaces inside scenario and FR text are collapsed by _normalize.
    reflowed = base.replace("a thing", "a   thing")
    reflowed = reflowed.replace("one thing", "one   thing")
    (repo / "specs" / "016-delta-derivation" / "spec.md").write_text(reflowed, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    second = _commit(repo, "016-delta-derivation/us1: US1 (#2)", env=env)

    fp1 = fingerprint(repo, first, "016-delta-derivation", "US1")
    fp2 = fingerprint(repo, second, "016-delta-derivation", "US1")
    assert fp1.digest == fp2.digest


def test_fingerprint_missing_file_refuses_with_named_finding(repo_builder: Callable[..., Path]) -> None:
    repo = repo_builder({"spec.md": _spec(stories=["US1"])})
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    sha = _commit(repo, "016-delta-derivation/us1: US1 (#1)", env=env, allow_empty=True)
    # The directory exists but spec.md did not at this revision? It did — so
    # remove the whole spec directory in a new commit to create a missing path.
    shutil.rmtree(repo / "specs" / "016-delta-derivation")
    _git(repo, "add", "-A", env=env)
    missing = _commit(repo, "remove spec dir", env=env)
    with pytest.raises(WorktreeError) as caught:
        fingerprint(repo, missing, "016-delta-derivation", "US1")
    assert "016-delta-derivation/spec.md" in str(caught.value)
