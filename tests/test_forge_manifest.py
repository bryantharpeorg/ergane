"""049-US5: a repository declares its forge, and an unknown one is refused.

Which forge a repository is on is a property of that repository — the same kind
of fact as `landing_branch` and `gates`, which are manifest keys for exactly that
reason. So `forge:` joins them, absent means `github`, and a name nothing is
registered under is refused by the loader with the registered names listed rather
than quietly resolved to the default.

Every test below answers "what edit would make this fail?" in its own docstring,
because the defect that has cost this repository most is a test that cannot fail.
The mutation transcripts proving each answer are committed at
`specs/049-forge-seam/evidence/us5-mutations.md`.

**Scope fence, asserted here rather than promised.** Teaching the parser a key
and spending it in this repository's own `ergane.yaml` are different acts, and
doing both in one diff is rejected at `CONFIG_ERROR` in 0.0s before any gate
command runs: the config gate parses a node's manifest with the *worker's
installed* parser, not the worktree's. 020/US1 died four times proving it.
`test_this_repositorys_own_manifest_does_not_spend_the_key` is that fence, and it
passed before this diff existed as well as after.

Nothing here registers a forge at import time. `tests/test_forge_seam.py` does,
deliberately, and computes its conformance parametrization from the registry at
its own import — a second module-level registration would enrol this file's
stand-ins in that suite depending on collection order. Every stand-in here is
installed with `monkeypatch` and gone by the end of the test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import factory.mergequeue.forge as forge_module
from factory.cli.init import _PROMPTS
from factory.mergequeue.forge import (
    DEFAULT_FORGE,
    Forge,
    resolve_forge_for_repo,
)
from factory.mergequeue.github_forge import GithubForge
from factory.verify.factory_yaml import (
    DEFAULT_FORGE_NAME,
    MANIFEST_NAME,
    _TOP_LEVEL_KEYS,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
)
from factory.verify.models import FactoryConfig
from tests.fake_forge import FakeForge, RepositoryModel

REPO_ROOT = Path(__file__).resolve().parents[1]

#: This repository's own manifest — the file US5-S4 says this story may not edit.
OWN_MANIFEST = REPO_ROOT / MANIFEST_NAME

#: Every manifest the fixture corpus ships, globbed rather than listed so a
#: fixture added later is covered by having been added. The corpus is asserted
#: non-empty where it is used: a glob that stopped matching passes forever.
FIXTURE_MANIFESTS = sorted(
    (REPO_ROOT / "tests" / "fixtures" / "target_repo").rglob("*.yaml")
)

#: A name nothing is registered under, in this suite or in production. Not
#: `conformance-probe`: `tests/test_forge_seam.py` registers that at import, and
#: a full-suite run would have it registered by the time these tests execute.
UNREGISTERED = "gitlab"

#: The stand-in this module registers, and only inside the test that needs it.
PROBE = "manifest-probe"


def _manifest(*, forge: str | None = None, version: int = 1) -> str:
    """A well-formed manifest, optionally declaring a forge."""
    lines = [f"version: {version}", "runtime: bwrap", "gates:", '  test: "true"']
    if forge is not None:
        lines.append(f"forge: {forge}")
    return "\n".join(lines) + "\n"


def _repo_with(tmp_path: Path, text: str | None) -> Path:
    """A directory that holds a manifest — or, when `text` is None, holds none."""
    repo = tmp_path / "target"
    repo.mkdir(parents=True)
    if text is not None:
        (repo / MANIFEST_NAME).write_text(text, encoding="utf-8")
    return repo


# --- US5-S1 / FR-014: a declared, registered forge parses ---------------------


def test_a_fixture_manifest_declaring_github_parses_and_resolves_to_github() -> None:
    """US5-S1. The fixture declares the key the schema knew nothing about until
    this story; before it, `_reject_unknown_keys` refused the file outright.

    Mutation: drop `forge` from `_TOP_LEVEL_KEYS` and this fails at the load with
    `unknown_key`; keep the key but drop the reader and it fails on the value.
    """
    path = REPO_ROOT / "tests/fixtures/target_repo/manifests/forge-github.yaml"

    config = load_factory_config(path)

    assert config.forge == "github"
    assert "forge: github" in path.read_text(encoding="utf-8"), (
        "the fixture must actually declare the key, or this proves nothing"
    )


def test_the_declared_name_is_what_the_door_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-014 end to end: the key is not decoration, it selects the forge.

    The stand-in is registered for this test only, so the assertion is that the
    *manifest* chose it — the same repository path with no manifest builds the
    GitHub forge two lines down, which is the control.

    Mutation: make `resolve_forge_for_repo` ignore the manifest and pass `None`
    to `resolve_forge` and this fails, because the probe is never built.
    """
    monkeypatch.setitem(
        forge_module._REGISTRY, PROBE, lambda **seams: FakeForge(RepositoryModel())
    )
    declared = _repo_with(tmp_path / "declared", _manifest(forge=PROBE))
    silent = _repo_with(tmp_path / "silent", _manifest())

    chosen = resolve_forge_for_repo(repo_path=str(declared))
    defaulted = resolve_forge_for_repo(repo_path=str(silent))

    assert isinstance(chosen, FakeForge)
    assert isinstance(defaulted, GithubForge)
    assert isinstance(chosen, Forge) and isinstance(defaulted, Forge)


# --- US5-S2 / FR-014: an unregistered forge is refused, never defaulted -------


def test_an_unregistered_forge_is_refused_with_the_registered_names_listed() -> None:
    """US5-S2, and the half that matters: *refused*, not defaulted.

    A deployment that asked for one forge and silently got another would open
    proposals, and land them, somewhere nobody was looking. The registered names
    are read off the registry at assert time rather than hardcoded, so the
    message stays honest when a forge is added.

    Mutation: return `DEFAULT_FORGE_NAME` instead of raising and this fails on
    the missing `pytest.raises` — a fallback cannot satisfy it.
    """
    path = REPO_ROOT / "tests/fixtures/target_repo/manifests/forge-unknown.yaml"

    with pytest.raises(FactoryConfigError) as excinfo:
        load_factory_config(path)

    error = excinfo.value
    assert error.rule == "forge"
    message = str(error)
    assert repr(UNREGISTERED) in message, "the message must name the value it refused"
    for name in forge_module.registered_forges():
        assert repr(name) in message, f"the message must list {name!r}"
    assert DEFAULT_FORGE in message


def test_the_door_refuses_an_unregistered_forge_rather_than_reaching_github(
    tmp_path: Path,
) -> None:
    """The refusal survives the trip through the door, which is where a silent
    fallback would actually hurt — a caller that got a `GithubForge` back for a
    manifest saying `gitlab` has already lost.

    Mutation: swallow every `FactoryConfigError` in `_manifest_forge_name` and
    this fails, because a forge comes back instead of an exception.
    """
    repo = _repo_with(tmp_path, _manifest(forge=UNREGISTERED))

    with pytest.raises(FactoryConfigError) as excinfo:
        resolve_forge_for_repo(repo_path=str(repo))

    assert excinfo.value.rule == "forge"


@pytest.mark.parametrize(
    "declared",
    ['""', '"   "', "", "true", "[github]"],
    ids=["empty", "blank", "null", "bool", "list"],
)
def test_a_declared_forge_that_is_not_a_name_is_refused(declared: str) -> None:
    """Declared means declared — this module's standing rule for optional keys.
    `forge:` with no value parses to `None`, and a blank string is the same
    operator mistake wearing a different hat; both would otherwise read as
    "declared" here and as "the default" everywhere else.

    Mutation: treat a falsy value as "absent" and the first three cases stop
    raising; skip the type check and `true` resolves a forge named `True`.
    """
    text = _manifest(forge=declared)

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "forge"


# --- US5-S3 / FR-014: absent means github, and nothing else moved -------------


def test_a_manifest_declaring_no_forge_resolves_to_github() -> None:
    """US5-S3. Every repository that exists today declares nothing, so this is
    the path that must not move.

    Mutation: make the absent branch return anything but `github` — or make the
    key required — and this fails.
    """
    text = _manifest()

    config = parse_factory_config(text)

    assert "forge" not in text
    assert config.forge == "github"


def test_every_existing_manifest_fixture_parses_exactly_as_it_did() -> None:
    """US5-S3's compatibility half, over the whole shipped corpus.

    "Unchanged" is checkable without the old tree: a manifest either parses and
    resolves the default forge, or it is refused for a rule that is not `forge`.
    Only the fixture written to be refused for its forge may be refused for it.
    Anti-vacuity first (plan trap 4) — a glob that matched nothing would prove
    nothing and pass forever.

    Mutation: make the absent key raise and every valid fixture flips to the
    `forge` rule; make `_reject_unknown_keys` refuse `forge` and the two new
    fixtures flip to `unknown_key`.
    """
    assert len(FIXTURE_MANIFESTS) >= 9, FIXTURE_MANIFESTS

    resolved: dict[str, str] = {}
    refused: dict[str, str] = {}
    for path in FIXTURE_MANIFESTS:
        try:
            resolved[path.name] = load_factory_config(path).forge
        except FactoryConfigError as error:
            refused[path.name] = error.rule

    assert resolved, "no fixture manifest parsed; this proved nothing"
    assert set(resolved.values()) == {DEFAULT_FORGE_NAME}, resolved
    assert sorted(n for n, rule in refused.items() if rule == "forge") == [
        "forge-unknown.yaml"
    ], refused


def test_the_default_forge_has_exactly_one_spelling() -> None:
    """The parser cannot import `factory.mergequeue.forge` at module scope — that
    module loads the shipped forges, which reach `factory.verify.gates`, which
    imports the parser — so the literal `github` is written in three places. This
    is what keeps them one fact.

    Mutation: change `DEFAULT_FORGE`, the parser's constant, or the dataclass
    default, alone, and this fails.
    """
    default = FactoryConfig(version=1, runtime="bwrap", gates={"test": "true"}).forge

    assert DEFAULT_FORGE_NAME == DEFAULT_FORGE == default == "github"


def test_a_manifest_broken_elsewhere_is_not_reported_as_a_forge_problem(
    tmp_path: Path,
) -> None:
    """The door resolves a forge; it is not a second manifest validator. A repo
    whose `version` is wrong has one defect, reported by the reader that owns it,
    and an operator should not first meet it as a forge lookup exploding.

    This is the *narrow* tolerance: it is scoped by rule, so the refusal US5-S2
    demands still travels (the test above proves that half). Mutation: re-raise
    every `FactoryConfigError` and this fails; swallow every one and US5-S2's
    door test fails. Neither shortcut passes both.
    """
    repo = _repo_with(tmp_path, _manifest(version=2))

    assert isinstance(resolve_forge_for_repo(repo_path=str(repo)), GithubForge)


def test_a_repository_with_no_manifest_still_resolves_the_default_forge(
    tmp_path: Path,
) -> None:
    """`ergane init --check` runs against repositories that have nothing yet, so
    a forge has to be resolvable before a manifest exists.

    Mutation: re-raise every `FactoryConfigError` in `_manifest_forge_name` and
    this fails on `missing_manifest`. The mutation this docstring *used* to name
    — "remove the `path.is_file()` guard" — came back green, because the absent
    file arrives as a `FactoryConfigError` the tolerance already covers, so the
    guard was a second path to an answer the first path already gave. The guard
    is gone; evidence M9 is the transcript.
    """
    repo = _repo_with(tmp_path, None)

    assert isinstance(resolve_forge_for_repo(repo_path=str(repo)), GithubForge)


def test_every_door_holding_a_repository_path_resolves_through_the_manifest() -> None:
    """T041, and trap 14 in the shape that bit this epic twice: the boundary has
    three doors — `merge_activities.py`, `workgraph/cli.py`, `cli/init.py` — and
    a migration that moves two leaves one resolving a forge the repository never
    declared, with nothing noticing.

    Swept rather than listed, and compared against a non-empty literal rather
    than `assert not offenders`, so a glob that stopped matching fails instead of
    going quiet. Mutation: put `resolve_forge(repo_path=…)` back into any one of
    the three and this fails.
    """
    callers = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "factory").rglob("*.py")
        if "resolve_forge(" in path.read_text(encoding="utf-8")
    }

    assert callers == {"factory/mergequeue/forge.py"}


def test_the_interview_asks_about_every_key_the_parser_knows() -> None:
    """`ergane init` drives its questions off `_TOP_LEVEL_KEYS`, which is the
    property that stops a new key from being invisible to the operator who has to
    declare it — and `_ask_for_key` does a bare `_PROMPTS[key]`, so a key added
    without a prompt does not degrade, it raises `KeyError` mid-interview.

    Mutation: add `forge` to `_TOP_LEVEL_KEYS` and not to `_PROMPTS` and this
    fails — which is exactly the state this story would otherwise have shipped.
    """
    assert set(_PROMPTS) == set(_TOP_LEVEL_KEYS)


# --- US5-S4 / FR-015: the story that teaches the key does not spend it --------


def test_this_repositorys_own_manifest_does_not_spend_the_key() -> None:
    """US5-S4, FR-015, plan trap 13 — and it passed before this diff too.

    The config gate parses a node's manifest with the *worker's installed*
    parser, not the worktree's, so a diff that both teaches `forge` and writes it
    into this repository's `ergane.yaml` is refused at `CONFIG_ERROR` in 0.0s,
    before any gate command runs, on every attempt, forever. The key becomes
    usable here only after this story lands and an operator restarts the worker —
    as a separate operator commit.

    Mutation: add `forge: github` to `ergane.yaml` and this fails. (In the
    factory it fails earlier and more expensively, which is the point.)
    """
    document = yaml.safe_load(OWN_MANIFEST.read_text(encoding="utf-8"))

    assert "forge" not in document, (
        "049-US5 teaches the manifest loader the `forge` key and must not also "
        "declare it here; the worker's installed parser has not learned it yet"
    )
    assert load_factory_config(OWN_MANIFEST).forge == DEFAULT_FORGE_NAME
