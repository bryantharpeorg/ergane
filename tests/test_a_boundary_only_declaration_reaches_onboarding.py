"""A boundary-only declaration reaches onboarding through the one shared seam (128 US2).

`boundary_only_gates` is declared in `ergane.yaml`, and `evaluate_repo` (128
US2, landed) now honours it — but `evaluate_repo` never reads a manifest; its
caller does. `onboard_target_repo` (FR-010) is the one seam the dispatch
activity, `ergane init --check` and `ergane repo onboard` all reach onboarding
through, so this module holds the story's load-bearing claim: **the list
travels from the manifest through that seam**, and a repository whose manifest
lists a declared gate the landing branch does not require passes where the same
repository without the line fails.

Every profile here is *derived*, never constructed: two manifests differing
only in the `boundary_only_gates` line, one modelled forge, one repository,
`onboard_target_repo(FakeForge(model), str(repo))` — the call shape
`tests/test_forge_readiness.py`'s differential already uses, over a model whose
gate tuple leaves the listed gate unrequired so the declaration is what decides
the verdict. The real forge is never handed a remote-less repository here: that
route fails a `repo_read` finding before `evaluate_repo` ever runs, and the
difference between the two halves disappears.

The fixture manifests are rewritten as `version: 2` bodies (trap 11) — the
fixture's own committed manifest is v1, and US1 registered the key v2-only, so
appending it to the v1 body is refused as an unknown key before onboarding
reads anything.
"""

from __future__ import annotations

from pathlib import Path

from factory.activities.merge_activities import onboard_target_repo
from factory.mergequeue.models import TargetRepoProfile
from tests.fake_forge import FakeForge, RepositoryModel
from tests.target_repo import build_target_repo

#: The fixture repo declares exactly these gates (its committed `ergane.yaml`).
FIXTURE_GATES = ("lint", "test", "typecheck")

#: A title source spelled the way a forge that is not GitHub would spell it —
#: mandatory in this story's model: without one the profile fails
#: `landing_title` in both halves and the differential dies (trap 12).
NEUTRAL_TITLE_SOURCE = "proposal-title"

#: The gate under test — declared by the fixture, required by nobody.
GATE_UNDER_TEST = "lint"

V2_MANIFEST = """\
version: 2
runtime: bwrap
gates:
  lint: "bash gates/lint.sh"
  test: "bash gates/test.sh"
  typecheck: "bash gates/typecheck.sh"
boundary_only_gates: [lint]
"""

V2_MANIFEST_WITHOUT = """\
version: 2
runtime: bwrap
gates:
  lint: "bash gates/lint.sh"
  test: "bash gates/test.sh"
  typecheck: "bash gates/typecheck.sh"
"""


def _model() -> RepositoryModel:
    """`_ready_model` with exactly one edit: the gate tuple narrowed (trap 9).

    The landing branch requires `test` and `typecheck` — `lint` is declared and
    *not* required, the only arrangement in which the boundary-only line is
    what decides the verdict. Everything else about `_ready_model` is kept,
    `title_source` included, or the profile fails `landing_title` in both
    halves and the pair stops differing (trap 12).
    """
    model = RepositoryModel(address="acme/app", default_branch="main")
    model.gate_on(
        "main",
        tuple(g for g in FIXTURE_GATES if g != GATE_UNDER_TEST),
        title_source=NEUTRAL_TITLE_SOURCE,
    )
    return model


def _manifest_for(repo: Path, *, listed: bool) -> None:
    """Overwrite the fixture's manifest with the v2 body this run needs.

    On disk rather than committed: `resolve_manifest_path` reads the file off
    disk, so the rewrite needs no commit — and the two halves of every
    differential below differ by exactly one line.
    """
    (repo / "ergane.yaml").write_text(
        V2_MANIFEST if listed else V2_MANIFEST_WITHOUT, encoding="utf-8"
    )


def _derive_profile(tmp_path: Path, *, listed: bool) -> TargetRepoProfile:
    """The profile `onboard_target_repo` itself produces — no list handed in.

    One repository from the fixture, the manifest rewritten to the v2 body,
    the modelled forge answering for it, and the *seam* doing the whole job:
    the caller names no list of its own, so this is the proof the list leaves
    the schema and reaches the judgment (FR-010, trap 9).
    """
    repo = build_target_repo(tmp_path / f"target-{listed}")
    _manifest_for(repo, listed=listed)
    return onboard_target_repo(FakeForge(_model()), str(repo))


def derive_onboarding_boundary_pair(
    tmp_path: Path,
) -> tuple[TargetRepoProfile, TargetRepoProfile]:
    """The `(listed, unlisted)` pair the refusal-site tests of 128 US2 feed in.

    T013 (FR-009) forbids those tests from constructing a profile — both the
    roadmap's park site and the child epic's re-evaluation already proceed on a
    hand-built `passed=True` — so they derive each half through the seam
    instead, from two manifests differing only in the declaration. This is the
    one shared fixture both surfaces drive; it lives beside the seam tests
    rather than in either surface's own module so neither copies the other.
    """
    return (
        _derive_profile(tmp_path, listed=True),
        _derive_profile(tmp_path, listed=False),
    )


# --- T014: the seam reads the list off the manifest ----------------------------


def test_a_listed_manifest_passes_where_the_unlisted_one_fails(tmp_path: Path) -> None:
    """T014 / US2-S5 / FR-010: one repository, one manifest line, two verdicts.

    The same repository, the same modelled forge, the same seam call — the only
    difference is the `boundary_only_gates:` line in the v2 manifest. With the
    line, the profile passes and the finding names the gate; without it,
    today's blocking finding stands and the repository is refused.

    Red before, green after: on the tree with US1 merged and the seam unthreaded,
    the listed half still carries the blocking `gate_check:lint` finding,
    because nothing reads the manifest's list. What edit would make this fail:
    thread the list anywhere but `onboard_target_repo` and both halves come
    back with whatever the forge said, the seam having decided nothing; or
    construct a profile by hand and this differential never existed.
    """
    listed = _derive_profile(tmp_path, listed=True)
    unlisted = _derive_profile(tmp_path, listed=False)

    assert listed.passed is True, [f for f in listed.findings if f.blocking]
    finding = [f for f in listed.findings if f.check == "gate_check:lint"][0]
    assert finding.passed is False
    assert finding.blocking is False, "the choice stays visible, not silent"
    assert finding.severity.name == "WARNING"
    assert "lint" in finding.detail

    assert unlisted.passed is False
    unlisted_finding = [f for f in unlisted.findings if f.check == "gate_check:lint"][0]
    assert unlisted_finding.passed is False
    assert unlisted_finding.blocking is True
    assert unlisted_finding.detail == (
        "gate 'lint' is declared in factory.yaml but the landing "
        "branch requires no check named 'lint' — add it to the "
        "branch's required checks so the forge runs the gate the "
        "factory declares"
    )


def test_the_two_manifests_differ_only_in_the_declaration(tmp_path: Path) -> None:
    """The differential's premise, proven rather than assumed.

    The two profiles' findings must be byte-identical apart from the
    `gate_check:lint` line — same checks, same order, same details — so "the
    declaration decided the verdict" is a claim about one line, not about two
    repositories that also differed elsewhere. What edit would make this fail:
    a fixture that changed anything else between the halves.
    """
    listed = _derive_profile(tmp_path, listed=True)
    unlisted = _derive_profile(tmp_path, listed=False)

    def _key(profile) -> list[tuple[str, bool, str]]:
        return [(f.check, f.passed, f.detail) for f in profile.findings]

    listed_keys = _key(listed)
    unlisted_keys = _key(unlisted)
    assert len(listed_keys) == len(unlisted_keys)
    only = [
        (a, b) for a, b in zip(listed_keys, unlisted_keys)
        if a != b
    ]
    assert len(only) == 1, f"exactly one finding may differ: {only}"
    (listed_finding, unlisted_finding) = only[0]
    assert listed_finding[0] == unlisted_finding[0] == "gate_check:lint"
    assert listed_finding[1] is False and unlisted_finding[1] is False
    assert listed_finding[2] != unlisted_finding[2]