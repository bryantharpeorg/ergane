"""120/US1: `ergane init --wire` over a repository that already has a manifest.

The defect these tests pin is data loss on a committed file. A repository held a
valid manifest declaring `standards` and a `ladder` block; `ergane init --wire
--non-interactive` re-derived a manifest from an interview whose vocabulary has
neither key, wrote it through `yaml.safe_dump`, and the operator was left with
nine lines where there had been a hundred and sixty-one. `init --check` then
called the result valid, because every key that vanished is optional.

Four assertions, one per acceptance scenario:

- **byte-identical** (US1-S1, plan trap 8), not "the parsed structures match".
  A structural assertion passes on the rewrite that dropped forty lines of
  operator prose, which is the failure being fixed. These read `read_bytes()`.
- **the wiring still happens** (US1-S2, trap 2). Not rewriting the manifest is
  not declining the job, so the assertion is the factory's *own* onboarding
  gate — `onboard_target_repo`, the judgment run at every epic start — passing
  against the wired model, plus the workflow file on disk.
- **the control** (US1-S3): a repository with no manifest still gets one, with
  optional keys absent exactly as today. Without this the story could be passed
  by an init that never writes anything.
- **an invalid manifest is a conversation** (US1-S4, trap 3): reported, and left
  on disk. The tempting reading of "keep a valid manifest" is "so overwrite an
  invalid one", which is worse than today — it destroys the file of an operator
  who is mid-edit.

And one more that is about *whose* answer counts (FR-001, trap 1): init's notion
of validity is the loader `init --check` asks, so the two verbs cannot disagree
about one file.

No real GitHub is reached: the forge model is `tests.test_ergane_init_wiring`'s
`FakeGitHub`, driven through the real `gh` argv surface, and every other outward
seam is bound by `bind_offline_seams`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.mergequeue import wiring
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
    resolve_manifest_path,
)

from tests.test_ergane_init import _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams
from tests.test_ergane_init_wiring import FakeGitHub, failed, onboarding_profile

#: A manifest of the shape the finding was reported against: valid, commented,
#: declaring `standards` and a `ladder` block. Every line below `version` is
#: something a rewrite loses — the two keys because init's interview has never
#: heard of them, the prose because `yaml.safe_dump` cannot write a comment.
CONFIGURED_MANIFEST = """\
# ergane.yaml — what "green" means for this repository.
#
# Written by hand and committed. The comments are the reason the values are
# what they are, and no emitter in this tree can reproduce them.

version: 2
runtime: bwrap

# One gate, because one gate is what this repo has.
gates:
  test: "uv run pytest -q"

# The document every dispatched agent is told to read and obey. This is the key
# whose loss started epic 120: every node afterwards runs with no standards at
# all, and nothing in the loop can tell that from a repo that declared none.
standards: docs/STANDARDS.md

# Declared, never inferred from a checked-out HEAD (constitution IX).
landing_branch: main

# A block init has no vocabulary for: absent from `_TOP_LEVEL_KEYS`, absent from
# `_PROMPTS`, and therefore absent from anything init writes.
ladder:
  max_attempts: 4
  debugger_cycles: 1
"""

#: A manifest the schema refuses, for the reason an operator mid-edit would
#: produce: a gate name schema v1 does not fix. It carries a comment too, so a
#: silent replacement is visible as more than a changed value.
REFUSED_MANIFEST = """\
# Halfway through adding a second gate. Do not overwrite this.
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
  smoke: "make smoke"
landing_branch: main
"""


def _repo_with_manifest(tmp_path: Path, manifest: str | None) -> Path:
    """A committed git repository, optionally already declaring a manifest."""
    files = {"README.md": "# app\n", "pyproject.toml": "[project]\nname='app'\n"}
    if manifest is not None:
        files[MANIFEST_NAME] = manifest
    return make_bare_repo(tmp_path, files)


def _wire_non_interactively(
    repo: Path, monkeypatch: pytest.MonkeyPatch, github: FakeGitHub | None = None
) -> Any:
    """`ergane init --wire --non-interactive <repo>`, every seam bound offline.

    The repository is *named* rather than inferred from the working directory:
    064/FR-007 refuses a non-interactive run whose root was resolved by walking
    up, and this is also the invocation the spec's own demonstration uses.
    """
    model = github if github is not None else FakeGitHub(owner_repo="acme/app")
    bind_offline_seams(monkeypatch, model)
    return _invoke(["init", "--wire", "--non-interactive", str(repo)], monkeypatch)


# ---------------------------------------------------------------------------
# T001 [US1-S1, trap 8] a valid manifest is byte-identical afterwards
# ---------------------------------------------------------------------------


def test_wire_leaves_a_valid_manifest_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S1: the file is compared as bytes, comments included.

    `assert yaml.safe_load(before) == yaml.safe_load(after)` would pass on the
    exact rewrite this story exists to stop, so the comparison is the bytes.
    """
    repo = _repo_with_manifest(tmp_path, CONFIGURED_MANIFEST)
    before = (repo / MANIFEST_NAME).read_bytes()

    result = _wire_non_interactively(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    after = (repo / MANIFEST_NAME).read_bytes()
    assert after == before, (
        "init rewrote a valid manifest; the diff an operator would have had to "
        "run before committing:\n"
        f"--- before\n{before.decode()}\n--- after\n{after.decode()}"
    )
    # Named individually so a future rewrite that happens to be byte-identical
    # for a *different* fixture still fails on the two keys that were lost.
    kept = parse_factory_config(after.decode("utf-8"))
    assert kept.standards == "docs/STANDARDS.md"
    assert kept.ladder.max_attempts == 4


# ---------------------------------------------------------------------------
# T002 [US1-S2, trap 2] keeping the manifest is not declining the job
# ---------------------------------------------------------------------------


def test_the_wiring_still_happens_when_the_manifest_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S2: `--wire` does the forge work it was asked to do.

    The primary assertion is not "some call was made": it is the factory's own
    onboarding gate, the judgment `EpicWorkflow` runs at every epic start,
    passing against the wired model. An init that early-returns on a valid
    manifest fails it, naming the check it skipped.
    """
    repo = _repo_with_manifest(tmp_path, CONFIGURED_MANIFEST)
    before = (repo / MANIFEST_NAME).read_bytes()
    github = FakeGitHub(owner_repo="acme/app", default_branch="main")

    result = _wire_non_interactively(repo, monkeypatch, github)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / MANIFEST_NAME).read_bytes() == before

    profile = onboarding_profile(repo, github)
    assert profile.passed, failed(profile)

    # The local half of the wiring, which needs no network and is what the
    # printed manual steps tell the operator to commit.
    workflow = repo / wiring.WORKFLOW_PATH
    assert workflow.is_file()
    # Wired from the gate the *kept* manifest declares, not from a re-derived one.
    assert "uv run pytest -q" in workflow.read_text(encoding="utf-8")
    assert "wiring:" in result.stdout


# ---------------------------------------------------------------------------
# T003 [US1-S3] the control: a repository with no manifest still gets one
# ---------------------------------------------------------------------------


def test_a_repository_with_no_manifest_still_gets_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S3: absent is still written, exactly as today.

    Without this the story is passable by an init that writes nothing at all,
    which would trade a destructive verb for a useless one.
    """
    repo = _repo_with_manifest(tmp_path, None)
    assert (repo / MANIFEST_NAME).exists() is False

    result = _wire_non_interactively(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    manifest = repo / MANIFEST_NAME
    assert manifest.is_file()
    written = parse_factory_config(manifest.read_text(encoding="utf-8"))
    assert written.version == 1
    assert written.runtime == "bwrap"
    assert written.gates == {"test": "uv run pytest -q"}
    assert written.landing_branch == "main"
    # 057/US1: `standards` is no longer omittable into nothing. A fresh repository
    # gets the default path and a seeded constitution.
    assert written.standards == ".specify/memory/constitution.md"
    assert written.roadmap is None
    assert "standards: .specify/memory/constitution.md" in manifest.read_text(encoding="utf-8")
    assert (repo / ".specify" / "memory" / "constitution.md").is_file()


# ---------------------------------------------------------------------------
# T004 [US1-S4, trap 3] an invalid manifest is reported, not replaced
# ---------------------------------------------------------------------------


def test_a_manifest_the_schema_refuses_is_reported_and_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S4: the operator is told what is wrong and keeps their file."""
    repo = _repo_with_manifest(tmp_path, REFUSED_MANIFEST)
    before = (repo / MANIFEST_NAME).read_bytes()

    result = _wire_non_interactively(repo, monkeypatch)

    assert result.code == EXIT_USER
    assert (repo / MANIFEST_NAME).read_bytes() == before

    output = result.stdout + result.stderr
    # The report names the file and quotes the loader's own complaint, so the
    # operator reads one phrasing of one fact whichever verb they ran.
    assert MANIFEST_NAME in output
    with pytest.raises(FactoryConfigError) as refusal:
        load_factory_config(repo / MANIFEST_NAME)
    assert refusal.value.problem in output


# ---------------------------------------------------------------------------
# T005 [FR-001, trap 1] one notion of validity, shared with `--check`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("manifest", "schema_accepts"),
    [(CONFIGURED_MANIFEST, True), (REFUSED_MANIFEST, False)],
    ids=["valid", "refused"],
)
def test_init_and_check_cannot_disagree_about_one_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: str,
    schema_accepts: bool,
) -> None:
    """FR-001: the verdict comes from the loader `--check` asks, not from init.

    An independent notion of validity inside init is how one file gets called
    valid by one verb and replaced by another. Both verbs are run over the same
    two files and required to agree: `--check`'s `factory_yaml` finding and
    init's decision to proceed move together.
    """
    repo = _repo_with_manifest(tmp_path, manifest)
    bind_offline_seams(monkeypatch, FakeGitHub(owner_repo="acme/app"))

    profile = init_module.check_repo(repo)
    finding = next(f for f in profile.findings if f.check == "factory_yaml")
    assert finding.passed is schema_accepts

    result = _invoke(["init", "--wire", "--non-interactive", str(repo)], monkeypatch)
    assert (result.code == EXIT_OK) is schema_accepts, result.stdout + result.stderr


def test_inits_verdict_is_the_loaders_verdict_quoted(tmp_path: Path) -> None:
    """FR-001 at the seam: the refusal is the loader's error, not a paraphrase.

    Read directly so the identity is pinned rather than inferred: init resolves
    the manifest with `resolve_manifest_path` — the one helper every reader in
    this tree calls — and loads it with `load_factory_config`, so a legacy
    filename and a schema rule are both answered the same way for both verbs.
    """
    repo = _repo_with_manifest(tmp_path, REFUSED_MANIFEST)
    path, _name = resolve_manifest_path(repo)

    with pytest.raises(FactoryConfigError) as loader:
        load_factory_config(path)
    with pytest.raises(Exception) as refusal:
        init_module._existing_manifest(repo)

    assert str(loader.value) in str(refusal.value)


def test_no_manifest_is_not_an_invalid_one(tmp_path: Path) -> None:
    """The other half of the seam: absent is `None`, and never a refusal.

    FR-003's mechanism. A reader that treated `missing_manifest` as "refuse and
    stop" would turn every fresh `ergane init` into an error.
    """
    repo = _repo_with_manifest(tmp_path, None)
    assert init_module._existing_manifest(repo) is None
