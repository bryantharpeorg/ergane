"""US3's pure onboarding judgment: repo facts + `factory.yaml` gates → findings.

`factory/mergequeue/onboard.py` is the judgment half of US3 (plan.md § US3). The
activity (`onboard_target_repo`) reads a repository through a forge and hands
over two records — a `RepositoryDescription`, and the `LandingPolicy` of the
branch a landing goes into — and this module turns those readings into a
`TargetRepoProfile` whose `findings` say, one check at a time, whether the repo
is ready for the factory to dispatch against it (FR-010).

Every check is a pure function of the readings it is handed, so this suite is
table-tested with no fakes at all: no forge, no git, no network. Each check fails
closed — a repo that fails any check is rejected for dispatch with a finding
that names what to change (spec US3 AS2).

The checks (049's US2 made them forge-neutral — spec 049 § *What the factory
actually needs*):

- the branch refuses a landing until named checks pass (Q2) — `gated_landing`;
- and then completes the merge with no human (Q3) — `autonomous_landing`;
- `factory.yaml` present, valid, non-empty gates — `factory_yaml`;
- the landing commit takes the proposal's title (Q5) — `landing_title`;
- every declared gate has a required check named *exactly* after it —
  `gate_check:<gate>`;
- every required check maps back to a declared gate (deterministic gates only,
  FR-003 — the structural guard that keeps the LLM judge out of CI) —
  `unknown_check:<name>`.

What a forge alone knows arrives on `RepositoryDescription.findings`;
`tests/test_forge_readiness.py` owns that story.
"""

from __future__ import annotations

from typing import Sequence

import pytest

from factory.mergequeue.forge import LandingPolicy, RepositoryDescription
from factory.mergequeue.models import Finding
from factory.mergequeue.onboard import InitFacts, evaluate_repo

REPO = "acme/widgets"
DEFAULT_BRANCH = "main"

#: A landing-title setting spelled the way a forge that is not GitHub would.
TITLE_SOURCE = "proposal-title"


def _reading(**over: object) -> RepositoryDescription:
    """A repository a forge could reach, saying nothing only that forge knows."""
    base = dict(address=REPO, default_branch=DEFAULT_BRANCH)
    return RepositoryDescription(**{**base, **over})  # type: ignore[arg-type]


def _policy(**over: object) -> LandingPolicy:
    """A branch answering every neutral question well, with named breaks."""
    base = dict(
        branch=DEFAULT_BRANCH, gates_on_named_checks=True,
        required_checks=("test",), lands_without_a_human=True,
        landing_title_from_proposal=True, landing_title_source=TITLE_SOURCE,
    )
    return LandingPolicy(**{**base, **over})  # type: ignore[arg-type]


def _findings(**facts: object):
    return evaluate_repo(**facts).findings


def _finding_by_check(findings: Sequence[object], check: str) -> object:
    for finding in findings:
        if finding.check == check:
            return finding
    raise AssertionError(f"no finding for check {check!r}; got {[f.check for f in findings]}")


# --- the happy path: every check passes, one finding each ---------------------


def test_a_fully_conforming_repo_passes_with_one_finding_per_check() -> None:
    """Gated + autonomous + titled + a check per gate → passed, all findings green.

    One passing Finding per check is the contract the operator preflight prints:
    `passed=True` is the conjunction, but each finding is reported so a human
    can see the repo was checked, not just that it passed.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(required_checks=("test", "lint", "typecheck")),
        declared_gates=("test", "lint", "typecheck"),
    )
    assert profile.passed is True
    checks = [f.check for f in profile.findings]
    assert "gated_landing" in checks
    assert "autonomous_landing" in checks
    assert "factory_yaml" in checks
    assert "landing_title" in checks
    assert "gate_check:test" in checks
    assert "gate_check:lint" in checks
    assert "gate_check:typecheck" in checks
    assert all(f.passed for f in profile.findings)


def test_required_checks_and_declared_gates_need_not_be_ordered_the_same() -> None:
    """The mapping is by name, not by position — a passing repo may list them differently."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(required_checks=("typecheck", "test", "lint")),
        declared_gates=("test", "lint", "typecheck"),
    )
    assert profile.passed is True


# --- each failing check, and the remedy its detail names ----------------------


def test_a_branch_that_gates_on_nothing_fails_carrying_the_forges_remedy() -> None:
    """Q2: a branch that will land a change no check ran against gates nothing."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(gates_on_named_checks=False),
        declared_gates=("test",),
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "gated_landing")
    assert finding.passed is False
    assert DEFAULT_BRANCH in finding.detail
    assert "configure the branch" in finding.detail


def test_a_declared_gate_with_no_required_check_names_the_missing_check() -> None:
    """`gate_check:<gate>` fails, naming the exact check the repo must add."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test", "lint"),
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "gate_check:lint")
    assert finding.passed is False
    assert "lint" in finding.detail


def test_a_required_check_with_no_declared_gate_is_rejected() -> None:
    """An unknown required check fails — deterministic gates only (FR-003).

    This is the structural guard that keeps the LLM judge out of CI: a required
    check that does not map to a declared gate is not something the factory
    asked for, and an unknown gate in the queue is one the factory would not
    control. The finding names the offending check.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(required_checks=("test", "judge")),
        declared_gates=("test",),
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "unknown_check:judge")
    assert finding.passed is False
    assert "judge" in finding.detail


def test_a_missing_or_malformed_factory_yaml_fails_naming_the_loaders_error() -> None:
    """A broken manifest is a failing finding carrying the 002 loader's error."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=(),
        factory_yaml_error="factory.yaml: [malformed_yaml] is not parseable YAML",
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "factory_yaml")
    assert finding.passed is False
    assert "malformed_yaml" in finding.detail


def test_factory_yaml_finding_key_is_unchanged() -> None:
    """US1-S5/FR-010: the `factory_yaml` finding key must not be renamed.

    The ledger counts recurrence by this stable key; renaming it would silently
    reset that history and corrupt recurrence-based constitution promotions.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
    )
    checks = [f.check for f in profile.findings]
    assert "factory_yaml" in checks
    finding = _finding_by_check(profile.findings, "factory_yaml")
    assert finding.passed is True


def test_every_failing_finding_detail_names_the_remedy() -> None:
    """Actionable: each failing detail says what to change, not just what is wrong."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(
            gates_on_named_checks=False,
            lands_without_a_human=False,
            landing_title_from_proposal=False,
            required_checks=("test", "judge"),
        ),
        declared_gates=("test",),
        factory_yaml_error="factory.yaml: [runtime] missing",
    )
    assert profile.passed is False
    for finding in profile.findings:
        if not finding.passed:
            assert finding.detail.strip(), f"finding {finding.check!r} has an empty detail"
            # A finding that names only the check's own slug is not actionable.
            assert finding.detail != finding.check


def test_a_fully_conforming_repo_with_no_gate_checks_extra_is_still_passed() -> None:
    """A single-gate repo (like Ergane itself) with matching checks passes."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
    )
    assert profile.passed is True
    assert _finding_by_check(profile.findings, "gate_check:test").passed is True


# --- Q5: the landing commit must carry the proposal's title -------------------


def test_a_landing_titled_from_anything_else_fails_with_the_forges_remedy() -> None:
    """The forge's own spelling travels as evidence and its own fix as remedy;
    neither is decided from here."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(
            landing_title_from_proposal=False,
            landing_title_source="commit-title",
            landing_title_remedy="title landings from the proposal",
        ),
        declared_gates=("test",),
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "landing_title")
    assert finding.passed is False
    assert "commit-title" in finding.detail
    assert "title landings from the proposal" in finding.detail


def test_a_forge_that_will_not_report_its_title_source_fails_closed() -> None:
    """An unreported title source is never a pass (FR-003), and a forge offering
    no remedy still gets a finding saying what is wrong."""
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(landing_title_from_proposal=False, landing_title_source=None),
        declared_gates=("test",),
    )
    assert profile.passed is False
    finding = _finding_by_check(profile.findings, "landing_title")
    assert finding.passed is False
    assert "unreadable" in finding.detail.lower()


# --- 034 US4: the same judgment, extended with the facts init creates ---------
#
# `ergane init --check` gathers four more facts — the runtime root and whether
# git ignores it, the registry entry, the landing branch, 033's probes — and
# hands them to *this* function rather than to a second one.  Same table style
# as everything above: pure facts in, findings out, no fakes at all.


def _init_facts(**overrides: object) -> InitFacts:
    """A conforming repo's init facts, with named breaks applied."""
    facts: dict[str, object] = dict(
        repo_root="/repos/widgets",
        runtime_root=".ergane",
        runtime_root_is_legacy=False,
        runtime_root_ignored=True,
        gitignore="/repos/widgets/.gitignore",
        registry_path="/state/ergane/repos.json",
        registry_slug="widgets",
        registry_error=None,
        landing_branch="main",
        landing_branch_exists=True,
        standards_path="docs/STANDARDS.md",
        standards_exists=True,
        control_plane=(Finding("temporal", True, "namespace `factory` exists"),),
        control_plane_error=None,
        schedule_id="ergane-roadmap-widgets",
        schedule_present=True,
        schedule_paused=False,
        schedule_drift=(),
        schedule_error=None,
    )
    facts.update(overrides)
    return InitFacts(**facts)  # type: ignore[arg-type]


def _judge(**overrides: object):
    """Judge a conforming repo whose init facts carry `overrides`."""
    return evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
        init_facts=_init_facts(**overrides),
    )


def test_init_facts_omitted_leaves_the_dispatch_judgment_untouched() -> None:
    """The 003 door passes no init facts, so it sees exactly the checks it always saw.

    The guard on "extend, never fork": the extension is invisible to a caller
    that gathers no init facts, so a check added here can never start refusing a
    dispatch that used to be allowed.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=("test",),
    )
    assert profile.passed is True
    assert [f.check for f in profile.findings] == [
        "gated_landing",
        "autonomous_landing",
        "factory_yaml",
        "landing_title",
        "gate_check:test",
    ]


def test_an_unreadable_registry_fails_its_own_finding_and_offers_rebuild() -> None:
    """A corrupt cache is reported as one finding, never as an aborted render."""
    profile = _judge(registry_slug=None, registry_error="is not parseable JSON")
    finding = _finding_by_check(profile.findings, "registry_entry")
    assert finding.passed is False
    assert "is not parseable JSON" in finding.detail
    assert "ergane repo rebuild" in finding.detail


def test_an_unloadable_manifest_leaves_the_landing_branch_unjudged_but_still_rendered() -> None:
    """No check is silently dropped: an unknown landing branch is a failing finding.

    The manifest's own finding still carries the loader's error, so the operator
    sees cause and consequence rather than one standing in for the other.
    """
    profile = evaluate_repo(
        repo=REPO,
        reading=_reading(),
        policy=_policy(),
        declared_gates=(),
        factory_yaml_error="ergane.yaml declares no gates",
        init_facts=_init_facts(landing_branch=None, landing_branch_exists=False),
    )
    manifest = _finding_by_check(profile.findings, "factory_yaml")
    assert manifest.passed is False
    branch = _finding_by_check(profile.findings, "landing_branch")
    assert branch.passed is False
    assert "manifest" in branch.detail.lower()


def test_a_failing_control_plane_probe_is_summarised_into_one_finding() -> None:
    """US4-S4: 033's probe detail is carried through, not replaced by a shrug."""
    profile = _judge(
        control_plane=(
            Finding("temporal", False, "timed out after 5s waiting for Temporal at localhost:7233"),
            Finding("memory", True, "skipped by declaration: memory.backend is `none`"),
        )
    )
    finding = _finding_by_check(profile.findings, "control_plane")
    assert finding.passed is False
    assert "temporal" in finding.detail
    assert "timed out after 5s waiting for Temporal at localhost:7233" in finding.detail
    # Repo-local findings still render — the whole point of scenario 4.
    assert _finding_by_check(profile.findings, "runtime_root_ignored").passed is True
    assert _finding_by_check(profile.findings, "registry_entry").passed is True
    assert _finding_by_check(profile.findings, "landing_branch").passed is True


def test_no_probes_and_no_error_is_still_a_failure_not_a_pass() -> None:
    """Fail closed: an empty probe set is unknown readiness, and unknown never passes."""
    profile = _judge(control_plane=())
    finding = _finding_by_check(profile.findings, "control_plane")
    assert finding.passed is False


def test_several_broken_preconditions_all_render_none_masked() -> None:
    """Trap 3: the render never stops at the first failure."""
    profile = _judge(
        runtime_root_ignored=False,
        registry_slug=None,
        landing_branch_exists=False,
        control_plane=(Finding("temporal", False, "not answering"),),
        schedule_present=False,
    )
    failed = [f.check for f in profile.findings if not f.passed]
    assert failed == [
        "runtime_root_ignored",
        "registry_entry",
        "landing_branch",
        "standards_floor",
        "control_plane",
        "roadmap_schedule",
    ]
