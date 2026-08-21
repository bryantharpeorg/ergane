"""061-US3: a gate that cannot fail is named as one, not reported as a pass.

The condition this file is about is the one nothing was looking for. A manifest
declaring `gates: {test: "true"}` is a valid manifest: it parses, it declares a
gate, the landing branch requires a check named `test`, and `ergane init
--check` printed `[PASS] gate_check:test — required check 'test' exists`. Every
word of that was true and the configuration it described was a factory that
lands whatever an agent writes, because the command behind the check exits 0
without running anything.

So the assertions here are about the *reported condition changing* between two
manifests that differ in one value — never about the detector having been
called (plan trap 1). Every test that shows a no-op recognised has a partner
showing a real command still reporting the pass it always did (plan trap 2):
a check that flagged every gate would be no more useful than one that flagged
none.

Three cells, one seam:

- `true`, `:` and the empty string are all recognised (FR-008). The first two
  reach the judgment through a real manifest and a real `ergane init --check`;
  the third cannot, because `factory.verify.factory_yaml._read_gates` refuses
  an empty command outright with `gate_command` — an empty gate is a *broken*
  manifest before it is a no-op one. It is exercised at `evaluate_repo`, which
  is the function `--check` judges with, so the parametrisation covers all
  three forms of the value at the place the value is judged.
- the finding does not fail `--check` (FR-009, plan trap 6): an operator
  evaluating Ergane without gates is making a choice, and a finding that
  blocked the run would be worked around by editing the manifest to a no-op the
  detector has never heard of.
- a freshly-initialised manifest declares no no-op gate at all (FR-010), which
  is the other half: the value `--check` now reports was one `ergane init`
  itself wrote on any repository whose tree suggested no gate command.

Fixtures reuse `tests.test_ergane_init_check.make_repo` and
`tests.test_ergane_init.make_bare_repo`, both of which commit through
`tests.target_repo.git_env` — an explicit `GIT_AUTHOR_*`/`GIT_COMMITTER_*`
identity rather than the host's. Plan trap 14: a CI runner has no git identity
and `git commit` exits 128 there while passing in a sandbox whose HOME is
seeded with a `.gitconfig`. No fixture here runs `git commit` any other way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
from factory.mergequeue.models import Finding, Severity, TargetRepoProfile
from factory.mergequeue.onboard import _is_noop_gate_command, evaluate_repo
from factory.verify.factory_yaml import (
    FactoryConfigError,
    MANIFEST_NAME,
    parse_factory_config,
)

from tests.fake_gh import FakeGh
from tests.test_ergane_init import _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, make_repo

REPO = "acme/widgets"

#: What the `wired` fixture hands a test: bind the outward seams, get the
#: scripted `gh` back. Spelled once so the signatures below fit on one line.
Wired = Callable[[], FakeGh]


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Wired:
    """Bind every outward seam, so no test here reaches GitHub or a control plane.

    `ergane init --check` probes the control plane and reads the repository
    through a forge; both are scripted, and `factory.roadmap.schedule` is
    pointed at a fake so the operator's live Temporal is untouchable from here.
    """

    def bind() -> FakeGh:
        return bind_offline_seams(monkeypatch)

    return bind


#: The three spellings FR-008 names. `true` and `:` are the shell's two
#: canonical do-nothings; the empty string is the value a manifest reaches by
#: declaring the key and writing nothing after it.
NOOP_COMMANDS = ("true", ":", "")

#: Commands that must keep reporting the pass they always did (plan trap 2).
#: `truthy` and `echo true` are the near misses a substring match would eat.
REAL_COMMANDS = ("uv run pytest -q", "bash gates/test.sh", "truthy", "echo true")


def _reading() -> RepositoryDescription:
    return RepositoryDescription(address=REPO, default_branch="main")


def _policy() -> LandingPolicy:
    return LandingPolicy(
        branch="main",
        gates_on_named_checks=True,
        required_checks=("test",),
        lands_without_a_human=True,
        landing_title_from_proposal=True,
        landing_title_source="proposal-title",
    )


def _judge(command: str) -> TargetRepoProfile:
    """The judgment `ergane init --check` runs, over one declared gate."""
    return evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
        gate_commands={"test": command},
    )


def _finding(profile: TargetRepoProfile, check: str) -> Finding:
    for finding in profile.findings:
        if finding.check == check:
            return finding
    raise AssertionError(
        f"no finding {check!r}; got {[f.check for f in profile.findings]}"
    )


def _checks(profile: TargetRepoProfile) -> list[str]:
    return [finding.check for finding in profile.findings]


def _noop_repo(tmp_path: Path, command: str, *, name: str = "widgets") -> Path:
    """A scaffolded repository whose only gate is `command`.

    `json.dumps` renders the command as a double-quoted YAML scalar, which is
    what keeps `true` a string rather than the boolean the parser would refuse
    as a gate command — the type confusion `factory_yaml`'s docstring names.
    """
    return make_repo(tmp_path, name=name, gates={"test": json.dumps(command)})


# --- T019 / US3-S1, US3-S2: each no-op form is a distinct finding -------------


@pytest.mark.parametrize("command", NOOP_COMMANDS)
def test_a_noop_gate_command_is_a_distinct_finding_not_a_pass(command: str) -> None:
    """US3-S1 and US3-S2 over all three forms, at the judgment `--check` uses.

    The finding's key and text are both asserted, because a key nobody can read
    and a text that does not say what is wrong are two different ways of
    reporting nothing. The negative half is the important one: the
    `gate_check:test` pass — the line an operator read as "gates work" — is not
    in this report at all.

    What edit would make this fail? Deleting `_is_noop_gate_command`'s body, or
    dropping any spelling from `_NOOP_GATE_COMMANDS`, or emitting the no-op
    finding *beside* the pass rather than instead of it.
    """
    profile = _judge(command)

    finding = _finding(profile, "noop_gate:test")
    assert finding.passed is False
    assert "gate_check:test" not in _checks(profile)

    detail = finding.detail
    assert repr(command) in detail, "the command the operator wrote is not quoted back"
    assert "no gate can fail" in detail
    assert "not a pass" in detail


@pytest.mark.parametrize("command", ["  true  ", "\ttrue\n", "   "])
def test_a_noop_gate_command_is_recognised_through_surrounding_whitespace(
    command: str,
) -> None:
    """`bash -c "  true  "` runs `true`; so does a command that is only spaces.

    `SubprocessGateExecutor` hands the string to `bash -c`, which does its own
    word splitting, so padding changes nothing about what runs and must change
    nothing about what is reported.
    """
    assert "noop_gate:test" in _checks(_judge(command))


def test_the_noop_finding_reaches_ergane_init_check_from_a_real_manifest(
    tmp_path: Path, wired: Wired
) -> None:
    """US3-S1 end to end: the operator's terminal, not just the judgment.

    `true` rather than `:` here and both forms in the parametrised CLI test
    below; this one asserts the rendered line an operator actually reads,
    including the `WARN` mark that distinguishes it from both a pass and a
    failure.
    """
    repo = _noop_repo(tmp_path, "true")
    registry.register("widgets", repo)
    wired()

    result = _invoke(["init", "--check", str(repo)])

    assert "[WARN] noop_gate:test" in result.stdout
    assert "[PASS] gate_check:test" not in result.stdout
    assert "no gate can fail" in result.stdout


@pytest.mark.parametrize("command", ["true", ":"])
def test_every_noop_form_a_manifest_can_carry_is_reported_by_the_cli(
    tmp_path: Path, wired: Wired, command: str
) -> None:
    """The two forms a *loadable* manifest can hold, through the real CLI.

    The empty string is absent by construction and the test below says why in
    an assertion rather than in a comment.
    """
    repo = _noop_repo(tmp_path, command, name=f"widgets-{len(command)}")
    registry.register(f"widgets-{len(command)}", repo)
    wired()

    result = _invoke(["init", "--check", str(repo)])

    assert "[WARN] noop_gate:test" in result.stdout
    assert repr(command) in result.stdout


def test_an_empty_gate_command_is_refused_by_the_manifest_parser_first() -> None:
    """Why the empty string is judged at `evaluate_repo` and not through the CLI.

    An empty command never reaches the gate↔check judgment, because the
    manifest carrying it does not load: `_read_gates` refuses it with
    `gate_command` and `--check` reports a failing `factory_yaml` instead. That
    is a stricter answer than the no-op finding, not a weaker one — but it makes
    the CLI the wrong seam for that cell of FR-008, and this assertion is what
    keeps the parametrisation above honest rather than the author's word for it.
    """
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config('version: 1\nruntime: bwrap\ngates:\n  test: ""\n')

    assert raised.value.rule == "gate_command"


# --- T020 / US3-S3: a real gate command still reports the existing pass -------


@pytest.mark.parametrize("command", REAL_COMMANDS)
def test_a_real_gate_command_reports_the_existing_pass_unchanged(command: str) -> None:
    """Plan trap 2: a check that flags everything is no better than one that flags
    nothing.

    The detail is asserted verbatim against the string this check has emitted
    since 003, because "unchanged" is the claim — a reworded pass would be a
    silent change to the report every operator and the dispatch path read.
    """
    profile = _judge(command)

    finding = _finding(profile, "gate_check:test")
    assert finding.passed is True
    assert finding.detail == "required check 'test' exists"
    assert finding.severity == Severity.ERROR
    assert not any(check.startswith("noop_gate:") for check in _checks(profile))
    assert profile.passed is True


def test_a_real_gate_command_reports_the_pass_through_the_cli(
    tmp_path: Path, wired: Wired
) -> None:
    """The control for the CLI test above: same command, same repo shape, one
    value different, and the reported condition differs."""
    repo = make_repo(tmp_path)  # gates default to `uv run pytest -q`
    registry.register("widgets", repo)
    wired()

    result = _invoke(["init", "--check", str(repo)])

    assert result.code == EXIT_OK
    assert "[PASS] gate_check:test" in result.stdout
    assert "noop_gate" not in result.stdout


def test_a_noop_gate_that_no_check_requires_still_fails_the_parity_check() -> None:
    """The two conditions are independent, and the blocking one still blocks.

    A gate that is a no-op *and* has no required check named after it is two
    problems; reporting only the advisory one would turn a failing repository
    into a passing one, which is the opposite of this story.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=LandingPolicy(
            branch="main",
            gates_on_named_checks=True,
            required_checks=(),
            lands_without_a_human=True,
            landing_title_from_proposal=True,
            landing_title_source="proposal-title",
        ),
        declared_gates=("test",),
        gate_commands={"test": "true"},
    )

    assert _finding(profile, "gate_check:test").passed is False
    assert _finding(profile, "noop_gate:test").passed is False
    assert profile.passed is False


def test_a_caller_that_states_no_gate_commands_judges_exactly_what_it_did_before() -> None:
    """`gate_commands` is additive: a caller that gathers none reports none.

    "Not stated" and "declared empty" are different facts, and collapsing them
    would make every call site that has not been taught to pass commands report
    every gate as a no-op.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
    )

    assert _finding(profile, "gate_check:test").passed is True
    assert not any(check.startswith("noop_gate:") for check in _checks(profile))


# --- T021 / US3-S4: the finding does not fail `--check` -----------------------


@pytest.mark.parametrize("command", NOOP_COMMANDS)
def test_the_noop_finding_does_not_fail_the_judgment(command: str) -> None:
    """FR-009 at the judgment: a warning is not a refusal.

    `passed` is what the dispatch path reads too (`RoadmapWorkflow` parks a spec
    on a failing profile), so a blocking no-op finding would stop every epic in
    a repository whose operator had deliberately turned gates off.
    """
    profile = _judge(command)

    assert _finding(profile, f"noop_gate:test").severity == Severity.WARNING
    assert profile.passed is True


def test_the_noop_finding_does_not_fail_ergane_init_check(
    tmp_path: Path, wired: Wired
) -> None:
    """US3-S4 as the exit status an operator's shell sees.

    Plan trap 6: the requirement is that the choice be visible, not that it be
    forbidden. A wall here gets worked around by editing the manifest to a no-op
    the detector has never heard of, and then nothing is visible at all.
    """
    repo = _noop_repo(tmp_path, "true")
    registry.register("widgets", repo)
    wired()

    result = _invoke(["init", "--check", str(repo)])

    assert result.code == EXIT_OK
    assert "[WARN] noop_gate:test" in result.stdout


def test_a_real_failing_check_still_fails_the_run_alongside_a_warning(
    tmp_path: Path, wired: Wired
) -> None:
    """The control for the exit status: `--check` can still refuse.

    Same repository, same no-op gate, one real precondition broken — and the
    exit code moves. Without this, a `--check` hardwired to 0 would pass every
    test above.
    """
    repo = _noop_repo(tmp_path, "true")
    (repo / ".gitignore").unlink()
    registry.register("widgets", repo)
    wired()

    result = _invoke(["init", "--check", str(repo)])

    assert result.code == EXIT_USER
    assert "[FAIL] runtime_root_ignored" in result.stdout
    assert "[WARN] noop_gate:test" in result.stdout


# --- T022 / US3-S5: a fresh manifest declares no no-op gate -------------------


def test_a_freshly_initialised_manifest_does_not_declare_true_as_a_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wired: Wired
) -> None:
    """FR-010. The repository with nothing to infer a gate from is the case.

    A tree with a `pyproject.toml` was always offered `uv run pytest -q`; a tree
    without one fell through to `_PLACEHOLDERS["gates"]`, and that is the value
    `--check` then reported as a passing gate. The manifest this writes is
    asserted against the detector itself, so the two halves of this story cannot
    drift apart: whatever init writes, `--check` must not call it a no-op.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    wired()

    result = _invoke(["init", "--non-interactive"], monkeypatch)

    assert result.code == EXIT_OK
    config = parse_factory_config((repo / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert config.gates, "a manifest with no gates would pass this vacuously"
    assert "true" not in config.gates.values()
    for name, command in config.gates.items():
        assert not _is_noop_gate_command(command), (
            f"init wrote gate {name!r} as {command!r}, which `--check` reports "
            "as a no-op"
        )


def test_a_freshly_initialised_manifest_is_reported_with_no_noop_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wired: Wired
) -> None:
    """FR-010 read back through the surface that made it visible.

    The end of SC-003's thread: init writes a manifest, `--check` judges it, and
    the no-op line is absent because there is no no-op to report.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    wired()

    assert _invoke(["init", "--non-interactive"], monkeypatch).code == EXIT_OK
    result = _invoke(["init", "--check", str(repo)], monkeypatch)

    assert "noop_gate" not in result.stdout


def test_the_placeholders_table_holds_no_value_that_could_become_a_live_gate() -> None:
    """US3-S5 read off `_PLACEHOLDERS` itself, as the scenario asks.

    The table's own comment calls these placeholders. A placeholder that is
    written into a manifest and then executed is not one, and the specific
    escape was `gates`. This asserts the key is gone rather than that its value
    changed, because a renamed no-op is the same defect.
    """
    assert "gates" not in init_module._PLACEHOLDERS
    for key, value in init_module._PLACEHOLDERS.items():
        assert not isinstance(value, dict), (
            f"_PLACEHOLDERS[{key!r}] is a mapping; the only mapping this table "
            "ever held was `gates`, and it escaped into live manifests"
        )


def test_a_tree_that_suggests_a_gate_command_still_gets_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wired: Wired
) -> None:
    """The control for FR-010: the inferred default is not what changed.

    Removing the placeholder must not remove the reading that made init useful
    on a Python repository, so the same command is still offered where the tree
    supports it.
    """
    repo = make_bare_repo(
        tmp_path, {"README.md": "# app\n", "pyproject.toml": "[project]\nname='app'\n"}
    )
    monkeypatch.chdir(repo)
    wired()

    assert _invoke(["init", "--non-interactive"], monkeypatch).code == EXIT_OK

    config = parse_factory_config((repo / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert config.gates == {"test": "uv run pytest -q"}
