"""Tests for `ergane init --check` (034 US4).

The check renders a repo's facts through the *existing* pure judgment —
`factory.mergequeue.onboard.evaluate_repo`, the one the 003 dispatch path uses —
extended with the facts init creates.  These tests cover what the pure table in
`test_onboard.py` cannot reach: the gathering (git, registry, 033's probes, read
without writing), the two doors rendering one judgment's findings byte for byte,
and the contract (no masking, non-zero exit on any failure, nothing mutated).

No test here reaches GitHub or a control plane: `gh` is scripted through the
`GhRunner` seam and the probes through `_controlplane_probe`.

Pasted evidence (plan trap 7) is at the bottom: the red run before the
implementation existed, and one mutation transcript per behaviour.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable, Iterable

import pytest

import factory.cli.init as init_module
import factory.workgraph.cli as workgraph_cli
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.controlplane.config import resolve_config_path
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge
from factory.mergequeue.models import Finding, Severity, TargetRepoProfile
from factory.roadmap import schedule as schedule_module

from tests.fake_gh import FakeGh
from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke

OWNER_REPO = "acme/widgets"

#: The `wired` fixture's type, spelled once so signatures fit on one line.
Wire = Callable[..., FakeGh]


# --- Fixtures: a repo on disk, a scripted `gh`, a scripted control plane ---

MANIFEST = """\
version: 1
runtime: bwrap
gates:
{gates}
standards: docs/STANDARDS.md
landing_branch: {landing_branch}
"""

def make_profile(findings: tuple[Finding, ...]) -> TargetRepoProfile:
    """A profile whose only purpose is to drive `render_check`."""
    return TargetRepoProfile(
        repo="acme/widgets",
        default_branch="main",
        visibility="public",
        queue_enabled=True,
        required_checks=(),
        declared_gates=(),
        findings=findings,
        passed=all(f.passed or not f.blocking for f in findings),
    )


def make_repo(
    tmp_path: Path,
    *,
    name: str = "widgets",
    gates: dict[str, str] | None = None,
    landing_branch: str = "main",
    gitignore_line: str | None = ".ergane/",
    runtime_root: str = ".ergane",
) -> Path:
    """A scaffolded repo: manifest, ignored runtime root, one commit on `main`.

    Built by hand, not by the interview: a check that only ever sees repos its
    own scaffold produced cannot report on an operator's repo.
    """
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")

    gate_lines = "\n".join(
        f"  {gate}: {command}" for gate, command in (gates or {"test": "uv run pytest -q"}).items()
    )
    (repo / "ergane.yaml").write_text(
        MANIFEST.format(gates=gate_lines, landing_branch=landing_branch),
        encoding="utf-8",
    )
    if gitignore_line is not None:
        (repo / ".gitignore").write_text(f"{gitignore_line}\n", encoding="utf-8")
    (repo / runtime_root).mkdir()
    (repo / "docs").mkdir()
    (repo / "docs" / "STANDARDS.md").write_text(
        "# standards\n\nSeeded from test-fixture (floor version 1.0.0).\n", encoding="utf-8"
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def conforming_gh(
    *,
    owner_repo: str = OWNER_REPO,
    branch: str = "main",
    visibility: str = "public",
    required_checks: Iterable[str] = ("test",),
    squash_title: str | None = "PR_TITLE",
) -> FakeGh:
    """A scripted `gh` describing a repo that satisfies the 003 checks."""
    fake = FakeGh()
    fake.expect_json(
        "repo",
        "view",
        payload={
            "nameWithOwner": owner_repo,
            "visibility": visibility,
            "defaultBranchRef": {"name": branch},
        },
    )
    fake.expect_json(
        "api",
        f"repos/{owner_repo}",
        payload={"squash_merge_commit_title": squash_title},
    )
    checks = [{"context": name} for name in required_checks]
    fake.expect_json(
        "api",
        f"repos/{owner_repo}/rules/branches/{branch}",
        payload=[
            {"type": "merge_queue", "parameters": {}},
            {"type": "required_status_checks", "parameters": {"required_status_checks": checks}},
        ],
    )
    return fake


HEALTHY_PROBES: list[Finding] = [
    Finding("temporal", True, "Temporal at localhost:7233 has namespace `factory`"),
    Finding("memory", True, "skipped by declaration: memory.backend is `none`"),
]

#: The `config.toml` a host with a control plane installed has. The Temporal it
#: declares is a name that does not resolve, so a test that somehow got past
#: both of `factory.roadmap.schedule`'s isolation guards would fail DNS rather
#: than find this host's live namespace.
INSTALLED_CONTROL_PLANE = """\
version = 1

[llm]
mode = "gateway"
base_url = "http://litellm.invalid"
master_key_env = "LITELLM_MASTER_KEY"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "control-plane.invalid:7233"
namespace = "offline-tests"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "TELEGRAM_CHAT_ID"
bot_token_env = "TELEGRAM_BOT_TOKEN"
"""


def bind_offline_seams(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeGh | None = None,
    *,
    probes: list[Finding] | None = None,
    probe_error: Exception | None = None,
    schedules: FakeScheduleServer | None = None,
    control_plane_installed: bool = True,
) -> FakeGh:
    """Bind every outward seam so no test can reach GitHub or a control plane.

    A function rather than only a fixture because every test that completes a
    full `ergane init` needs it: init's last act is the check (FR-010), and an
    unbound seam would spawn the real `gh` and deliver a real Telegram probe.

    034/US6 added the third seam.  It is bound here rather than per-test for the
    same reason as the other two, with one extra: the operator's Temporal holds
    the live `ergane-roadmap` schedule, and `ergane init` now *writes* a
    schedule.  `factory.roadmap.schedule` refuses to connect under pytest at
    all, so a forgotten binding fails loudly; this makes the bound case the
    default anyway.

    050/US1 added the fourth thing this promises, and it is a *file* rather than
    a seam: `ergane init` now refuses to publish a schedule at all when the
    control-plane config cannot be read (FR-001), and the suite's session
    fixture points `ERGANE_CONFIG_PATH` at a path nothing creates.  A helper
    that promised a healthy control plane while leaving no config behind was
    promising something incoherent — every init driven through it would have
    taken the refusal path, and the three tests in
    `test_ergane_init_schedule.py` that read a created schedule off the backend
    said so.  Pass `control_plane_installed=False` for a host where `ergane
    install` has never run.
    """
    gh = fake if fake is not None else conforming_gh()

    if control_plane_installed:
        # Beside the path the session fixture already points at, so this stays
        # inside pytest's own temporary tree; the binding is monkeypatched, so a
        # test that wants a different config just sets one after this returns.
        config = resolve_config_path().parent / "offline-control-plane.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(INSTALLED_CONTROL_PLANE, encoding="utf-8")
        monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(config))
        monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(config))

    control_plane = schedules if schedules is not None else FakeScheduleServer()
    if schedules is None:
        # A healthy control plane by default, exactly as `conforming_gh()`
        # describes a healthy GitHub: every repo already in this test's registry
        # gets the schedule `ergane init` would have created for it.  A test
        # that means to break the schedule passes its own server.
        for entry in registry.load_registry().entries:
            seed(control_plane, desired_for(entry.path, slug=entry.slug))

    async def open_schedule_client() -> FakeScheduleServer:
        return control_plane

    monkeypatch.setattr(
        schedule_module, "_schedule_client_factory", open_schedule_client
    )
    monkeypatch.setattr(
        init_module,
        "_forge_factory",
        lambda *, repo_path: GithubForge(GhClient(repo=repo_path, runner=gh)),
    )
    monkeypatch.setattr(
        workgraph_cli,
        "_onboard_client_factory",
        lambda *, repo_path: GithubForge(GhClient(repo=repo_path, runner=gh)),
    )

    findings = HEALTHY_PROBES if probes is None else probes

    def probe() -> tuple[list[Finding], int]:
        if probe_error is not None:
            raise probe_error
        return list(findings), 0 if all(f.passed for f in findings) else 1

    monkeypatch.setattr(init_module, "_controlplane_probe", probe)
    return gh


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Wire:
    """`bind_offline_seams`, curried with this test's monkeypatch."""

    def bind(
        fake: FakeGh | None = None,
        *,
        probes: list[Finding] | None = None,
        probe_error: Exception | None = None,
        schedules: FakeScheduleServer | None = None,
    ) -> FakeGh:
        return bind_offline_seams(
            monkeypatch,
            fake,
            probes=probes,
            probe_error=probe_error,
            schedules=schedules,
        )

    return bind


def _checks(profile: TargetRepoProfile) -> dict[str, bool]:
    return {finding.check: finding.passed for finding in profile.findings}


def _failing(profile: TargetRepoProfile) -> list[str]:
    return [finding.check for finding in profile.findings if not finding.passed]


def _detail(profile: TargetRepoProfile, check: str) -> str:
    for finding in profile.findings:
        if finding.check == check:
            return finding.detail
    raise AssertionError(f"no finding {check!r}; got {[f.check for f in profile.findings]}")


# --- T026 / US4-S1: the all-pass case ---

def test_a_scaffolded_registered_wired_repo_passes_every_finding(tmp_path: Path, wired: Wire) -> None:
    """US4-S1: every finding passes and the exit code is 0."""
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired()

    profile = init_module.check_repo(repo)

    assert _failing(profile) == []
    assert profile.passed is True
    assert set(_checks(profile)) == {
        "visibility",
        "gated_landing",
        "autonomous_landing",
        "factory_yaml",
        "landing_title",
        "gate_check:test",
        # 064/US2 added `resolved_root`: which repository the report is about,
        # said in a finding rather than only in the header line.
        "resolved_root",
        "runtime_root_ignored",
        "registry_entry",
        "landing_branch",
        # 057/US1: a repository must declare and contain a standards document.
        "standards",
        # 057/US3: the seeded floor's age is advisory and visible.
        "standards_floor",
        "control_plane",
        "roadmap_schedule",
    }

    result = _invoke(["init", "--check", str(repo)])
    assert result.code == EXIT_OK
    assert "[PASS] runtime_root_ignored" in result.stdout
    assert "[FAIL]" not in result.stdout


# --- T027 / SC-004: each precondition broken one at a time ---

def test_a_runtime_root_missing_from_gitignore_fails_naming_the_line(tmp_path: Path, wired: Wire) -> None:
    """US4-S2: the failure this check exists to prevent, with the line to add.

    A runtime root reaching git history is how a node commits megabytes of its
    own transcripts onto a landing branch, so the detail must be copy-pasteable.
    """
    repo = make_repo(tmp_path, gitignore_line=None)
    registry.register("widgets", repo)
    wired()

    profile = init_module.check_repo(repo)

    assert _failing(profile) == ["runtime_root_ignored"]
    detail = _detail(profile, "runtime_root_ignored")
    assert ".ergane/" in detail
    assert str(repo / ".gitignore") in detail

    result = _invoke(["init", "--check", str(repo)])
    assert result.code == EXIT_USER


def test_a_declared_gate_with_no_required_check_fails_the_parity_finding(tmp_path: Path, wired: Wire) -> None:
    """US4-S3: the *existing* parity finding, unchanged — one judgment, two doors."""
    repo = make_repo(
        tmp_path,
        gates={"test": "uv run pytest -q", "lint": "uv run ruff check ."},
    )
    registry.register("widgets", repo)
    wired(conforming_gh(required_checks=("test",)))

    profile = init_module.check_repo(repo)

    assert _failing(profile) == ["gate_check:lint"]
    detail = _detail(profile, "gate_check:lint")
    assert "lint" in detail
    assert "required" in detail


def test_a_repo_with_no_registry_entry_fails_only_the_registry_finding(tmp_path: Path, wired: Wire) -> None:
    """Dropping the registry entry flips exactly that finding (SC-004)."""
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired()
    before = _checks(init_module.check_repo(repo))

    # Break exactly one precondition: the registry is a cache, so removing it is
    # the honest way to drop the entry.
    registry.resolve_registry_path().unlink()

    after = _checks(init_module.check_repo(repo))

    assert set(before) == set(after)
    # Two findings, one break.  The slug lives only in the registry and it is
    # what names the schedule, so dropping the entry does not merely fail the
    # registry check — it makes the schedule check unanswerable, and an
    # unanswerable check fails.  The same honest cascade `factory_yaml` already
    # has over `landing_branch`; nothing is *masked*, which is the rule.
    assert [check for check in after if not after[check]] == [
        "registry_entry",
        "roadmap_schedule",
    ]
    detail = _detail(init_module.check_repo(repo), "registry_entry")
    assert str(repo.resolve()) in detail
    assert str(registry.resolve_registry_path()) in detail
    assert "ergane init" in detail


def test_renaming_the_landing_branch_fails_only_the_landing_branch_finding(tmp_path: Path, wired: Wire) -> None:
    """The manifest declares a branch the repo no longer has (SC-004)."""
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired()
    before = _checks(init_module.check_repo(repo))
    assert all(before.values())

    _git(repo, "branch", "-m", "main", "trunk")

    after = _checks(init_module.check_repo(repo))
    assert [check for check in after if not after[check]] == ["landing_branch"]
    detail = _detail(init_module.check_repo(repo), "landing_branch")
    assert "main" in detail
    assert f"git -C {repo.resolve()} branch main" in detail


# --- T028 / US4-S4: nothing masks anything ---

def test_a_down_control_plane_fails_its_finding_and_every_repo_local_finding_renders(tmp_path: Path, wired: Wire) -> None:
    """US4-S4: 033's probe detail is carried through; the rest of the report survives."""
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired(
        probes=[
            Finding("temporal", False, "timed out after 5s waiting for Temporal at localhost:7233"),
            Finding("llm", True, "completed a 1-token completion"),
        ]
    )

    profile = init_module.check_repo(repo)

    assert _failing(profile) == ["control_plane"]
    assert "timed out after 5s waiting for Temporal at localhost:7233" in _detail(
        profile, "control_plane"
    )
    for check in ("runtime_root_ignored", "registry_entry", "landing_branch", "gate_check:test"):
        assert _checks(profile)[check] is True

    result = _invoke(["init", "--check", str(repo)])
    assert result.code == EXIT_USER
    assert "[PASS] runtime_root_ignored" in result.stdout
    assert "[FAIL] control_plane" in result.stdout


def test_a_probe_that_raises_does_not_abort_the_render(tmp_path: Path, wired: Wire) -> None:
    """Trap 3's real failure mode: an exception from one probe must not eat the report."""
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired(probe_error=RuntimeError("no control-plane config at /etc/ergane.toml"))

    profile = init_module.check_repo(repo)

    assert _failing(profile) == ["control_plane"]
    assert "/etc/ergane.toml" in _detail(profile, "control_plane")
    assert _checks(profile)["runtime_root_ignored"] is True


def test_a_repo_gh_cannot_read_still_renders_every_init_finding(tmp_path: Path, wired: Wire) -> None:
    """The spec's edge case: no GitHub remote at all — registered, not dispatchable.

    The `gh` refusal dominates the 003 findings, and the repo-local judgments
    still render; otherwise a repo with no remote would silently skip the check
    that keeps its runtime root out of git.
    """
    repo = make_repo(tmp_path, gitignore_line=None)
    registry.register("widgets", repo)
    refusing = FakeGh()
    refusing.expect_error("repo", "view", stderr="no git remotes found")
    wired(refusing)

    profile = init_module.check_repo(repo)

    checks = _checks(profile)
    assert checks["repo_read"] is False
    assert checks["runtime_root_ignored"] is False
    assert checks["registry_entry"] is True
    assert checks["landing_branch"] is True
    assert checks["control_plane"] is True


# --- T029 / FR-010: one judgment, two doors ---

def test_both_doors_render_identical_parity_findings(tmp_path: Path, wired: Wire) -> None:
    """The dispatch door and the init door agree on every 003 finding, verbatim.

    Not "in spirit": the same `(check, passed, detail)` triples, because both
    come from one call into `evaluate_repo`.  A second judgment that agreed today
    and drifted next month is what this asserts against.
    """
    repo = make_repo(
        tmp_path,
        gates={"test": "uv run pytest -q", "lint": "uv run ruff check ."},
    )
    registry.register("widgets", repo)
    wired(conforming_gh(required_checks=("test", "typecheck")))

    from factory.activities.merge_activities import onboard_target_repo

    dispatch_door = onboard_target_repo(
        workgraph_cli._onboard_client_factory(repo_path=str(repo)), str(repo)
    )
    init_door = init_module.check_repo(repo)

    dispatch_findings = [(f.check, f.passed, f.detail) for f in dispatch_door.findings]
    init_findings = [(f.check, f.passed, f.detail) for f in init_door.findings]

    assert dispatch_findings, "the dispatch door rendered nothing to compare against"
    assert init_findings[: len(dispatch_findings)] == dispatch_findings
    # And the init door adds exactly its own checks on top.
    assert [check for check, _, _ in init_findings[len(dispatch_findings) :]] == [
        # 064/US2: the repository the rest of these findings are about is named
        # first, so an operator reads *which* repo before reading its verdicts.
        "resolved_root",
        "runtime_root_ignored",
        "registry_entry",
        "landing_branch",
        # 057/US1: a repository must declare and contain a standards document.
        "standards",
        # 057/US3: the seeded floor's age is advisory and visible.
        "standards_floor",
        "control_plane",
        "roadmap_schedule",
    ]
    # The parity failures both doors care about are present and identical.
    assert ("gate_check:lint", False) in [(c, p) for c, p, _ in dispatch_findings]
    assert ("unknown_check:typecheck", False) in [(c, p) for c, p, _ in dispatch_findings]


def test_both_doors_report_a_listed_gate_as_a_warning_not_a_refusal(
    tmp_path: Path, wired: Wire
) -> None:
    """128-US2 / FR-010: the boundary-only declaration reaches *both* doors.

    `test_both_doors_render_identical_parity_findings` above drives the same
    repository through the dispatch door (`onboard_target_repo`) and the init
    door (`check_repo`) and holds the two to byte-identical triples. This case
    extends that parity into the new behaviour, over a manifest that *declares*
    the list rather than restating it anywhere: the same wiring requires `test`
    and `typecheck` over a manifest declaring `test` and `lint`, so `lint` is
    exactly a declared gate the branch does not require — and the manifest
    names it boundary-only.

    Asserted on the mark, not on equality alone: the two doors rendered
    identical triples before this story and after it, so a case that only
    re-asserted equality would be green on a diff that threaded nothing. Both
    halves must show `gate_check:lint` as `[WARN]` — non-blocking on *both*
    doors — or one door is reporting a verdict the other does not.

    What edit would make this fail: an init-side fact gatherer or forge factory
    that loads the manifest a second time and drops the list.
    """
    repo = make_repo(
        tmp_path,
        gates={
            "test": "uv run pytest -q",
            "lint": "uv run ruff check .",
            "typecheck": "uv run mypy .",
        },
    )
    registry.register("widgets", repo)
    wired(conforming_gh(required_checks=("test", "typecheck")))
    # `make_repo` writes a v1 body; the key is v2-only (128 FR-004), so the
    # list is declared by rewriting the manifest as a v2 one — on disk, which
    # `resolve_manifest_path` reads, no commit needed. The branch requires
    # `test` and `typecheck` over gates declaring all three, so `lint` is
    # exactly the declared gate the branch does not require, and it is the one
    # the manifest lists boundary-only.
    manifest = repo / "ergane.yaml"
    manifest.write_text(
        """\
version: 2
runtime: bwrap
gates:
  test: "uv run pytest -q"
  lint: "uv run ruff check ."
  typecheck: "uv run mypy ."
boundary_only_gates: [lint]
standards: docs/STANDARDS.md
landing_branch: main
""",
        encoding="utf-8",
    )

    from factory.activities.merge_activities import onboard_target_repo

    dispatch_door = onboard_target_repo(
        workgraph_cli._onboard_client_factory(repo_path=str(repo)), str(repo)
    )
    init_door = init_module.check_repo(repo)

    for door, profile in (("dispatch", dispatch_door), ("init", init_door)):
        lint = [f for f in profile.findings if f.check == "gate_check:lint"]
        assert lint, f"the {door} door rendered no gate_check:lint finding"
        assert lint[0].mark == "WARN", f"{door} door: {lint[0].mark} — {lint[0].detail}"
        assert lint[0].blocking is False
        assert "lint" in lint[0].detail
        # The verdict each door reports carries the same shape of truth: the
        # finding is reported without refusing the repository.
        assert profile.passed is True, [
            f.check for f in profile.findings if f.blocking
        ]


GUARDED_SLUGS = {
    "resolved_root",
    "runtime_root_ignored",
    "runtime_root_migration",
    "registry_entry",
    "landing_branch",
    "standards",
    "control_plane",
    "roadmap_schedule",
}
GUARDED_PREFIXES = ("gate_check:", "unknown_check:")

JUDGMENT = Path(__file__).resolve().parents[1] / "factory" / "mergequeue" / "onboard.py"


def _finding_slugs(module: Path) -> set[str]:
    """Every check slug this module passes as `Finding(...)`'s first argument."""
    slugs: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")) != "Finding":
            continue
        first: ast.expr | None = node.args[0] if node.args else None
        for keyword in node.keywords:
            if keyword.arg == "check":
                first = keyword.value
        if isinstance(first, ast.JoinedStr) and first.values:
            first = first.values[0]  # an f-string's literal head, e.g. `gate_check:`
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            slugs.add(first.value)
    return slugs


def test_only_the_shared_judgment_builds_the_readiness_findings() -> None:
    """No module outside `onboard.py` constructs a readiness finding.

    The guard is worth only as much as its own coverage, so it asserts first
    that the judgment does build all of them — otherwise a rename would leave a
    test that passes because it is looking for nothing.
    """
    judged = _finding_slugs(JUDGMENT)
    assert GUARDED_SLUGS <= judged
    assert any(slug.startswith(GUARDED_PREFIXES) for slug in judged)

    offenders: dict[str, set[str]] = {}
    package = JUDGMENT.parents[1]
    for module in sorted(package.rglob("*.py")):
        if module == JUDGMENT:
            continue
        found: set[str] = set()
        for slug in _finding_slugs(module):
            if slug in GUARDED_SLUGS or slug.startswith(GUARDED_PREFIXES):
                found.add(slug)
        if found:
            offenders[str(module.relative_to(package.parent))] = found
    assert offenders == {}


# --- Trap 1: a command that only looks must not write ---

def _tree(root: Path) -> dict[str, bytes]:
    """Every path under `root` except git's own bookkeeping, with its bytes."""
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".git":
            continue
        snapshot[str(relative)] = path.read_bytes() if path.is_file() else b"<dir>"
    return snapshot


def test_check_writes_nothing_anywhere(tmp_path: Path, wired: Wire) -> None:
    """The read-only property, proven rather than asserted (trap 1).

    Working tree, refs, history, status and the engine's registry are compared
    either side of a run that actually produced a report.
    """
    repo = make_repo(tmp_path)
    registry.register("widgets", repo)
    wired()
    state_home = registry.resolve_state_home()

    tree_before = _tree(repo)
    state_before = _tree(state_home)
    refs_before = _git(repo, "show-ref")
    log_before = _git(repo, "log", "--format=%H %s")
    status_before = _git(repo, "status", "--porcelain")

    result = _invoke(["init", "--check", str(repo)])

    assert result.code == EXIT_OK
    assert "[PASS] registry_entry" in result.stdout, "the run must have done its job"
    assert _tree(repo) == tree_before
    assert _tree(state_home) == state_before
    assert _git(repo, "show-ref") == refs_before
    assert _git(repo, "log", "--format=%H %s") == log_before
    assert _git(repo, "status", "--porcelain") == status_before


def test_check_does_not_create_the_runtime_root_it_is_judging(tmp_path: Path, wired: Wire) -> None:
    """A repo with no runtime root is reported on, not repaired.

    `resolve_factory_root()` — the worker's resolver — *creates* `.ergane/` when
    neither name is present, and resolves against the process's cwd rather than
    the repo under judgment.  A check built on it would scaffold behind the
    operator's back and judge the wrong directory.
    """
    repo = make_repo(tmp_path)
    (repo / ".ergane").rmdir()
    registry.register("widgets", repo)
    wired()

    profile = init_module.check_repo(repo)

    assert (repo / ".ergane").exists() is False
    assert (Path.cwd() / ".ergane").resolve() != (repo / ".ergane").resolve()
    assert _checks(profile)["runtime_root_ignored"] is True


def test_a_repo_still_on_the_legacy_runtime_root_is_judged_on_that_root(tmp_path: Path, wired: Wire) -> None:
    """Trap 12: an unmigrated repo has `.factory/`, and that is the root to ignore."""
    repo = make_repo(tmp_path, gitignore_line=".factory/", runtime_root=".factory")
    registry.register("widgets", repo)
    wired()

    profile = init_module.check_repo(repo)

    assert _checks(profile)["runtime_root_ignored"] is True
    assert _detail(profile, "runtime_root_ignored").startswith(".factory/")
    assert _checks(profile)["runtime_root_migration"] is False
    assert "ergane repo migrate-runtime-root" in _detail(profile, "runtime_root_migration")


# --- FR-010: the check is the automatic last act of a full init ---

def test_a_full_init_ends_by_running_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wired: Wire
) -> None:
    """FR-010: init's last act is the check, and its report reaches the operator.

    The exit code stays 0 because the repo-local work succeeded: a written and
    registered scaffold is not undone by a merge queue nobody has wired yet
    (US3-S3), and the printed findings say what remains.
    """
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text("# fresh\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")

    wired(probes=[Finding("temporal", False, "Temporal at localhost:7233 did not answer")])
    prompter = ScriptedPrompter(
        # version, runtime, gates, timeouts, standards, landing_branch, roadmap,
        # forge (049/US5, omitted — absent means github), slug
        ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", "", "", "", "", "", "", "widgets"]
    )
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)

    result = _invoke(["init", str(repo)])

    assert result.code == EXIT_OK
    assert "readiness" in result.stdout.lower()
    assert "[PASS] registry_entry" in result.stdout
    assert "[FAIL] control_plane" in result.stdout


# --- US5: every non-passing readiness line names its fix -----------------------


def _render_check(profile: TargetRepoProfile, remedy: dict[str, str] | None = None) -> str:
    """Call the function under test without touching a real repository."""
    return init_module.render_check(profile, Path("/dev/null"), "ergane.yaml", remedy=remedy)


US5_PROFILE: tuple[Finding, ...] = (
    Finding("well_known_pass", True, "this one passes"),
    Finding("well_known_fail", False, "blocking detail", severity=Severity.ERROR),
    Finding("well_known_warn", False, "warning detail", severity=Severity.WARNING),
    Finding("unknown_check", False, "something obscure failed", severity=Severity.ERROR),
)

US5_REMEDY: dict[str, str] = {
    "well_known_fail": "ergane fix blocking",
    "well_known_warn": "ergane fix warning",
}


def test_render_check_with_remedy_emits_fix_clause_on_non_passing_lines() -> None:
    """US5-S1: blocking and warning lines carry the command that clears them.

    Passing lines stay clean, and a check the table does not know falls back to
    naming `ergane init --check` rather than printing nothing.
    """
    profile = make_profile(US5_PROFILE)
    report = _render_check(profile, remedy=US5_REMEDY)

    lines = report.splitlines()

    pass_line = next(line for line in lines if "well_known_pass" in line)
    fail_line = next(line for line in lines if "well_known_fail" in line)
    warn_line = next(line for line in lines if "well_known_warn" in line)
    unknown_line = next(line for line in lines if "unknown_check" in line)

    assert pass_line == "  [PASS] well_known_pass: this one passes"
    assert "ergane fix blocking" in fail_line
    assert "ergane fix warning" in warn_line
    assert "ergane init --check" in unknown_line
    # Each fix clause must be clearly delimited from the detail.
    assert fail_line == "  [FAIL] well_known_fail: blocking detail — fix: ergane fix blocking"
    assert warn_line == "  [WARN] well_known_warn: warning detail — fix: ergane fix warning"
    assert (
        unknown_line
        == "  [FAIL] unknown_check: something obscure failed — fix: run `ergane init --check`"
    )


def test_render_check_without_remedy_is_byte_identical_to_baseline() -> None:
    """US5-S2: omitting the remedy table leaves today's output untouched."""
    profile = make_profile(US5_PROFILE)
    report = _render_check(profile)

    expected = """\
ergane readiness for /dev/null (ergane.yaml)
  [PASS] well_known_pass: this one passes
  [FAIL] well_known_fail: blocking detail
  [WARN] well_known_warn: warning detail
  [FAIL] unknown_check: something obscure failed
2 of 4 checks failed, 1 warned"""
    assert report == expected


# =============================================================================
# Pasted evidence (constitution VIII / D-037): the judge sees this file, never a
# terminal.  Every transcript below was produced by the commands shown.
# =============================================================================

# --- the red run, before any implementation existed (commit f30d2e8) ---------
#
# $ uv run pytest -q tests/test_onboard.py
# E   ImportError: cannot import name 'InitFacts' from 'factory.mergequeue.onboard'
# !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
# 1 error in 0.19s
#
# $ uv run pytest -q tests/test_ergane_init_check.py
# E       AttributeError: <module 'factory.cli.init' ...> has no attribute
#         '_gh_client_factory'
# 14 failed in 0.26s
#
# --- mutation transcripts ----------------------------------------------------
# One production change at a time, applied, run, reverted.  Command for every
# row: `uv run pytest -q tests/test_onboard.py tests/test_ergane_init_check.py`
# (rows M3 and M11-M17 ran the second module alone).  Counts are that run's
# summary line; each is red only because the mutation is.
#
# M1  onboard.py `if facts.runtime_root_ignored` -> `if True`  3 failed, 30 passed
# M2  the gitignore detail stops naming the line to add        1 failed, 32 passed
# M3  init.py `_git_ignores` returns True for everything       2 failed, 12 passed
# M4  registry_entry always passes                             2 failed, 31 passed
# M5  landing_branch always passes                             2 failed, 31 passed
# M6  an unloadable manifest emits no landing_branch finding   1 failed, 18 passed
# M7  control_plane calls every probe set a pass               4 failed, 29 passed
# M8  an empty probe set reads as reachable                    1 failed, 18 passed
# M9  evaluate_init_facts returns after the first failure      3 failed, 30 passed
# M10 merge_activities stops passing init_facts through       11 failed,  3 passed
# M11 _profile_from_gh_failure drops evaluate_init_facts       1 failed, 13 passed
# M12 _control_plane_facts loses its try/except                1 failed, 13 passed
# M13 resolve_repo_runtime_root mkdir()s the missing root      1 failed, 13 passed
# M14 resolve_repo_runtime_root ignores the legacy name        1 failed, 13 passed
# M15 run_check always returns EXIT_OK                         2 failed, 12 passed
# M16 init_command stops calling run_check                     1 failed, 13 passed
# M17 init.py builds a Finding("registry_entry", ...) of its own
#                                                              1 failed, 13 passed
#
# The names pytest printed, for the two mutations whose blast radius is the
# contract itself:
#
# M9 (no masking):
# FAILED tests/test_onboard.py::test_several_broken_preconditions_all_render_none_masked
# FAILED tests/test_ergane_init_check.py::test_a_repo_with_no_registry_entry_fails_only_the_registry_finding
# FAILED tests/test_ergane_init_check.py::test_a_repo_gh_cannot_read_still_renders_every_init_finding
#
# M11 (a gh refusal must not eat the repo-local findings):
# FAILED tests/test_ergane_init_check.py::test_a_repo_gh_cannot_read_still_renders_every_init_finding
#
# --- the full suite, after the implementation --------------------------------
#
# $ uv run pytest -q
# 2653 passed, 44 skipped, 4 warnings in 287.42s (0:04:47)
#
# One earlier whole-suite run failed test_pause_roadmap_parks_dispatch_between_epics
# (tests/test_roadmap_operator_surface.py), which polls a live Temporal test
# server under a 30s wall-clock timeout.  It passes alone, passes alone with
# these changes stashed, and passed on the run above; nothing in this diff is
# reachable from the roadmap workflow.  Recorded rather than hidden.
