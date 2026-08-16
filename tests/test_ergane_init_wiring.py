"""Tests for `ergane init --wire` (034 US3): GitHub wired to enforce the declarations.

The spec's Independent Test names "a disposable public GitHub repo". That is not
reachable from a test suite that must be green offline, in a sandbox, on a fresh
clone — and worse, it is unprovable from a diff (constitution Principle VIII), so
a criterion resting on it can never be checked by the judge. It is reconstructed
here as a **model of a GitHub repository** driven through the real `gh` argv
surface: `FakeGitHub` below.

Why that model cannot make a vacuous test pass — the trap this repository has
paid for five times in two days:

- It is a *model*, not a recorder. Its read verbs (`gh repo view`, `gh api
  repos/X`, `gh api repos/X/rules/branches/Y`) are served from mutable state, and
  the only thing that changes that state is a **write verb the production code
  actually issued**. The test never hands the model the answer.
- The payload of every write is read back off the temp file `GhClient` wrote for
  `gh api --input`. The model learns what production sent, never what the test
  intended.
- The primary assertion is not on the model's call log. It runs the factory's own
  reader — `onboard_target_repo` -> `evaluate_repo`, the structural gate at every
  epic start (`EpicWorkflow._onboard_target`) — against the wired model and
  requires `profile.passed`. With the production wiring doing nothing, the model
  keeps its fresh-repo state (`squash_merge_commit_title: COMMIT_OR_PR_TITLE`, no
  rulesets), so `squash_title`, `merge_queue` and every `gate_check:*` finding
  fails and the test goes red.
- Any `gh` invocation the model does not implement raises immediately, so wiring
  cannot pass by issuing something GitHub would have rejected.

**No real GitHub repository is touched by anything in this file**, and no
mutating `gh` call is issued against one: every `GhClient` here is constructed
with `runner=<the model>`.

MUTATION EVIDENCE (pasted per behaviour, per Principle VIII — run in this
worktree; each mutation was reverted immediately after its transcript):
<<<MUTATIONS>>>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
import yaml

import factory.cli.init as init_module
from factory.activities.merge_activities import onboard_target_repo
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.mergequeue import wiring
from factory.mergequeue.gh import GhClient
from factory.mergequeue.onboard import evaluate_repo
from factory.verify.factory_yaml import _SUPPORTED_VERSION, parse_factory_config

from tests.test_ergane_init import Run, ScriptedPrompter, _invoke, make_bare_repo

# -----------------------------------------------------------------------------
# The model of a GitHub repository
# -----------------------------------------------------------------------------


class _Result:
    """What one scripted `gh` invocation returned — the shape `GhClient` reads."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeGitHub:
    """A mutable model of one GitHub repository, driven through the `gh` argv surface.

    Reads are served from state; writes change it. The starting state is a
    *fresh* public repo as GitHub actually creates one: no rulesets at all, and
    `squash_merge_commit_title` at GitHub's default `COMMIT_OR_PR_TITLE` — so
    three of `evaluate_repo`'s five checks fail until something wires them.
    """

    def __init__(
        self,
        *,
        owner_repo: str = "acme/app",
        visibility: str = "PUBLIC",
        default_branch: str = "main",
        squash_merge_commit_title: str = "COMMIT_OR_PR_TITLE",
        gh_installed: bool = True,
        logged_in: bool = True,
    ) -> None:
        self.owner_repo = owner_repo
        self.visibility = visibility
        self.default_branch = default_branch
        self.squash_merge_commit_title = squash_merge_commit_title
        self.gh_installed = gh_installed
        self.logged_in = logged_in
        self.rulesets: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, ...]] = []
        self._next_id = 1

    # --- the runner seam -----------------------------------------------------

    def __call__(self, argv: Sequence[str], cwd: str) -> _Result:
        args = tuple(argv)
        self.calls.append(args)

        if not self.gh_installed:
            # What an absent binary really does to `subprocess.run`.
            raise FileNotFoundError(2, "No such file or directory: 'gh'")

        if args[:2] == ("auth", "status"):
            if self.logged_in:
                return _Result(stdout=f"github.com\n  Logged in to github.com\n")
            return _Result(
                stderr=(
                    "You are not logged into any GitHub hosts. "
                    "To log in, run: gh auth login"
                ),
                returncode=1,
            )

        if args[:2] == ("repo", "view"):
            return self._json(
                {
                    "nameWithOwner": self.owner_repo,
                    "visibility": self.visibility,
                    "defaultBranchRef": {"name": self.default_branch},
                }
            )

        if args[:1] == ("api",):
            return self._api(args)

        raise AssertionError(f"FakeGitHub does not model `gh {' '.join(args)}`")

    # --- the REST surface ----------------------------------------------------

    def _api(self, args: tuple[str, ...]) -> _Result:
        method = "GET"
        endpoint: str | None = None
        fields: dict[str, str] = {}
        body: Any = None

        index = 1
        while index < len(args):
            token = args[index]
            if token == "-X":
                method = args[index + 1]
                index += 2
            elif token == "-f":
                key, _, value = args[index + 1].partition("=")
                fields[key] = value
                index += 2
            elif token == "--input":
                # The payload is read off the file production actually wrote.
                body = json.loads(Path(args[index + 1]).read_text(encoding="utf-8"))
                index += 2
            elif token.startswith("-"):
                index += 1
            else:
                if endpoint is None:
                    endpoint = token
                index += 1

        if endpoint is None:
            raise AssertionError(f"`gh {' '.join(args)}` names no endpoint")

        prefix = f"repos/{self.owner_repo}"
        if endpoint == prefix:
            if method == "PATCH":
                if "squash_merge_commit_title" in fields:
                    self.squash_merge_commit_title = fields["squash_merge_commit_title"]
                return self._json(self._repo_payload())
            return self._json(self._repo_payload())

        if endpoint == f"{prefix}/rulesets":
            if method == "POST":
                return self._json(self._create_ruleset(body))
            return self._json(
                [
                    {"id": rid, "name": rs["name"], "target": rs.get("target", "branch")}
                    for rid, rs in sorted(self.rulesets.items())
                ]
            )

        if endpoint.startswith(f"{prefix}/rulesets/"):
            ruleset_id = int(endpoint.rsplit("/", 1)[1])
            if ruleset_id not in self.rulesets:
                return _Result(stderr="gh: Not Found (HTTP 404)", returncode=1)
            if method == "PUT":
                stored = dict(body or {})
                stored["id"] = ruleset_id
                self.rulesets[ruleset_id] = stored
            return self._json(self.rulesets[ruleset_id])

        if endpoint.startswith(f"{prefix}/rules/branches/"):
            branch = endpoint.rsplit("/", 1)[1]
            return self._json(self._rules_for_branch(branch))

        if endpoint.startswith(f"{prefix}/branches/"):
            # Classic protection: this repo configures none, and GitHub answers
            # 404 "Branch not protected" — an answer, not a failure.
            return _Result(stderr="gh: Branch not protected (HTTP 404)", returncode=1)

        raise AssertionError(f"FakeGitHub does not model the endpoint {endpoint!r}")

    def _repo_payload(self) -> dict[str, Any]:
        return {
            "full_name": self.owner_repo,
            "visibility": self.visibility.lower(),
            "default_branch": self.default_branch,
            "squash_merge_commit_title": self.squash_merge_commit_title,
        }

    def _create_ruleset(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise AssertionError("ruleset creation sent no JSON body")
        ruleset_id = self._next_id
        self._next_id += 1
        stored = dict(body)
        stored["id"] = ruleset_id
        self.rulesets[ruleset_id] = stored
        return stored

    def _rules_for_branch(self, branch: str) -> list[dict[str, Any]]:
        """The flat rule list GitHub returns for one branch, across all rulesets."""
        ref = f"refs/heads/{branch}"
        rules: list[dict[str, Any]] = []
        for ruleset_id, ruleset in sorted(self.rulesets.items()):
            if str(ruleset.get("enforcement") or "") != "active":
                continue
            conditions = ruleset.get("conditions") or {}
            ref_name = conditions.get("ref_name") or {}
            include = ref_name.get("include") or []
            matched = ref in include or "~ALL" in include
            if "~DEFAULT_BRANCH" in include and branch == self.default_branch:
                matched = True
            if not matched:
                continue
            for rule in ruleset.get("rules") or []:
                entry = dict(rule)
                entry["ruleset_id"] = ruleset_id
                rules.append(entry)
        return rules

    @staticmethod
    def _json(payload: Any) -> _Result:
        return _Result(stdout=json.dumps(payload))

    # --- what the tests interrogate ------------------------------------------

    def snapshot(self) -> str:
        """Every byte of repo state this model holds, order-independent."""
        return json.dumps(
            {
                "visibility": self.visibility,
                "default_branch": self.default_branch,
                "squash_merge_commit_title": self.squash_merge_commit_title,
                "rulesets": {str(k): v for k, v in self.rulesets.items()},
            },
            sort_keys=True,
        )

    def mutations(self) -> list[tuple[str, ...]]:
        """Every invocation that asked GitHub to change something."""
        found: list[tuple[str, ...]] = []
        for call in self.calls:
            if "-X" not in call:
                continue
            method = call[call.index("-X") + 1]
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                found.append(call)
        return found


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

TWO_GATES = 'test: "uv run pytest -q"\nsmoke: "bash smoke.sh"'


def answers(*, gates: str = TWO_GATES, landing_branch: str = "main", slug: str = "myapp") -> list[str]:
    """The scripted interview: version, runtime, gates, timeouts, standards, branch, slug."""
    return [str(_SUPPORTED_VERSION), "bwrap", gates, "", "", landing_branch, slug]


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    """Run `ergane init` with a scripted interview and an injected GitHub model."""

    def runner(*argv: str, script: list[str], github: FakeGitHub) -> Run:
        prompter = ScriptedPrompter(script)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        monkeypatch.setattr(
            init_module,
            "_gh_client_factory",
            lambda repo_root: GhClient(repo=str(repo_root), runner=github),
        )
        return _invoke(list(argv))

    return runner


def onboarding_profile(repo: Path, github: FakeGitHub) -> Any:
    """The factory's own structural gate, run against the wired model.

    This is `EpicWorkflow._onboard_target`'s judgment verbatim: the same reader,
    the same pure `evaluate_repo`. Nothing in this helper knows what the wiring
    intended to do.
    """
    return onboard_target_repo(GhClient(repo=str(repo), runner=github), str(repo))


def failed(profile: Any) -> list[tuple[str, str]]:
    return [(f.check, f.detail) for f in profile.findings if not f.passed]


# -----------------------------------------------------------------------------
# T019 / spec US3-S1 — wiring produces a repo the factory will dispatch against
# -----------------------------------------------------------------------------


def test_wiring_makes_the_repo_pass_the_factorys_own_onboarding_gate(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S1: queue enabled on the landing branch, required checks = the declared gates.

    The assertion is the one that matters in the real world: after wiring, the
    structural gate that runs at *every* epic start passes. All five of
    `evaluate_repo`'s checks are named explicitly so a future check cannot be
    silently dropped from this proof.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(owner_repo="acme/app", default_branch="main")

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr

    profile = onboarding_profile(repo, github)
    assert profile.passed, failed(profile)

    checks = {f.check for f in profile.findings}
    assert checks == {
        "visibility",
        "merge_queue",
        "factory_yaml",
        "squash_title",
        "gate_check:test",
        "gate_check:smoke",
    }
    assert profile.default_branch == "main"
    assert sorted(profile.required_checks) == ["smoke", "test"]


def test_wiring_writes_a_workflow_whose_jobs_are_the_gates(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S1: the scaffolded workflow defines jobs named `test` and `smoke`.

    The job *name* is what GitHub names the check run after, which is the half of
    the gate<->check contract that lives in the repo's tree rather than in its
    settings.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)
    assert result.code == EXIT_OK, result.stderr

    workflow = repo / wiring.WORKFLOW_PATH
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")

    parsed = yaml.safe_load(text)
    jobs = parsed["jobs"]
    assert [job["name"] for job in jobs.values()] == ["test", "smoke"]

    commands = {
        job["name"]: [step["run"] for step in job["steps"] if "run" in step]
        for job in jobs.values()
    }
    assert commands == {"test": ["uv run pytest -q"], "smoke": ["bash smoke.sh"]}

    # The queue runs its checks on the merge group; a workflow that only fires on
    # `pull_request` produces no check for the queue to wait on.
    assert "merge_group:" in text

    # And the operator is told to commit it, like everything else init writes.
    assert str(wiring.WORKFLOW_PATH) in result.stdout


EXPECTED_WORKFLOW = """\
# Generated by `ergane init --wire`: one job per gate declared in ergane.yaml.
#
# The job names below ARE the gate names. GitHub names each check run after the
# job's `name`, and the merge queue is configured to require a check named
# exactly after each declared gate. Rename a job here and the factory refuses to
# dispatch against this repo, because the gate it declares has no check.
#
# TODO(operator): add whatever toolchain setup your gate commands need (a
# language runtime, a package manager). `ergane init` writes the gates you
# declared; it does not guess how to install them.
name: ergane gates

on:
  pull_request:
  merge_group:

jobs:
  test:
    name: "test"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: "test"
        run: "uv run pytest -q"

  smoke:
    name: "smoke"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: "smoke"
        run: "bash smoke.sh"
"""


def test_the_rendered_workflow_is_exactly_one_job_per_gate_and_nothing_else() -> None:
    """The generated file, verbatim in the diff — nothing to take on trust."""
    rendered = wiring.render_gates_workflow(
        {"test": "uv run pytest -q", "smoke": "bash smoke.sh"}
    )
    assert rendered == EXPECTED_WORKFLOW


# -----------------------------------------------------------------------------
# T022 / plan trap 9 — the generated workflow declares exactly the gates
# -----------------------------------------------------------------------------


def test_the_generated_jobs_produce_no_unknown_check_finding(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """Trap 9: an extra required job makes the repo fail its own check one step later.

    The generated workflow's job names are fed back through the pure judgment as
    the queue's required checks. Any job the manifest does not declare surfaces
    as `unknown_check:<name>` — the finding that keeps the LLM judge out of CI.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()
    assert wired("init", "--wire", str(repo), script=answers(), github=github).code == EXIT_OK

    parsed = yaml.safe_load((repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8"))
    job_names = [job["name"] for job in parsed["jobs"].values()]

    profile = evaluate_repo(
        repo="acme/app",
        default_branch="main",
        visibility="public",
        queue_enabled=True,
        required_checks=job_names,
        declared_gates=["test", "smoke"],
        squash_merge_commit_title="PR_TITLE",
    )

    assert [f.check for f in profile.findings if f.check.startswith("unknown_check:")] == []
    assert profile.passed, failed(profile)


# -----------------------------------------------------------------------------
# T020 / spec US3-S2 — idempotence
# -----------------------------------------------------------------------------


def test_rewiring_reports_already_satisfied_and_changes_nothing(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S2: a re-run reports already-satisfied, issues no write, and alters no byte.

    "Changes nothing" is asserted twice and both ways round: the model's whole
    state is byte-compared across the re-run, *and* the re-run is required to
    have issued no mutating call at all. The first catches a write that happens
    to be a no-op; the second catches a write that GitHub would have counted as
    a change.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()

    first = wired("init", "--wire", str(repo), script=answers(), github=github)
    assert first.code == EXIT_OK, first.stderr
    assert github.mutations(), "the first run must actually wire something"

    before = github.snapshot()
    workflow_before = (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8")
    github.calls.clear()

    second = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert second.code == EXIT_OK, second.stderr
    assert github.snapshot() == before
    assert github.mutations() == []
    assert (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8") == workflow_before

    assert second.stdout.count(wiring.ALREADY_SATISFIED) >= 3
    assert onboarding_profile(repo, github).passed


# -----------------------------------------------------------------------------
# T021 / spec US3-S3 — the visibility refusal
# -----------------------------------------------------------------------------


def test_a_private_repo_is_refused_at_the_visibility_check_citing_d007(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S3: refused with D-007 and both remedies; the scaffold half is still usable."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(visibility="PRIVATE")

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_USER
    assert "D-007" in result.stderr
    # Both remedies, named.
    assert "public" in result.stderr.lower()
    assert "plan" in result.stderr.lower()

    # Refused at the check, before anything was changed.
    assert github.mutations() == []

    # The scaffold half of init survives the refusal and still parses.
    manifest = repo / "ergane.yaml"
    assert manifest.is_file()
    config = parse_factory_config(manifest.read_text(encoding="utf-8"), source="ergane.yaml")
    assert sorted(config.gates) == ["smoke", "test"]
    assert ".ergane/" in (repo / ".gitignore").read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# T021 / spec US3-S4 — `gh` absent or unauthenticated
# -----------------------------------------------------------------------------


def test_an_absent_gh_is_refused_naming_the_prerequisite_and_the_manual_steps(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S4: a missing `gh` is a refusal that names the prerequisite, not a traceback."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(gh_installed=False)

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_USER
    assert "unexpected error" not in result.stderr
    assert "Traceback" not in result.stderr
    assert "gh" in result.stderr
    assert "not installed" in result.stderr.lower()
    # The manual wiring steps are offered instead.
    assert "gh api -X PATCH repos/" in result.stderr
    assert "squash_merge_commit_title=PR_TITLE" in result.stderr
    assert "test" in result.stderr and "smoke" in result.stderr
    assert github.mutations() == []


def test_an_unauthenticated_gh_is_refused_naming_the_exact_login_command(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """S4: the refusal carries `gh auth login` verbatim and the manual steps."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(logged_in=False)

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_USER
    assert "gh auth login" in result.stderr
    assert "Traceback" not in result.stderr
    assert "manual" in result.stderr.lower()
    assert github.mutations() == []
    # Not even a read got through, so nothing was half-wired.
    assert [c for c in github.calls if c[:2] == ("repo", "view")] == []


# -----------------------------------------------------------------------------
# Plan trap 2 — the queue rule is read for GitHub's default branch
# -----------------------------------------------------------------------------


def test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The declared landing branch is what gets wired; the divergence is said aloud.

    `evaluate_repo` reads the queue for GitHub's *default* branch, not for the
    manifest's `landing_branch`. Wiring one and validating the other silently is
    the defect; this test pins the decision: wire the branch the factory actually
    lands on, and report — loudly, with the remedy — that onboarding will keep
    failing until the two agree. The last two assertions prove the report is
    telling the truth rather than reciting a warning.
    """
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(default_branch="main")

    result = wired(
        "init", "--wire", str(repo),
        script=answers(landing_branch="release"),
        github=github,
    )

    assert result.code == EXIT_OK, result.stderr

    # Wired the declared landing branch, and only it.
    assert github._rules_for_branch("release"), "the landing branch was not wired"
    assert github._rules_for_branch("main") == []

    # Said so, with the remedy.
    assert "release" in result.stdout
    assert "default branch" in result.stdout
    assert "gh repo edit --default-branch release" in result.stdout

    # And the warning is true: the factory's gate reads `main` and still fails.
    profile = onboarding_profile(repo, github)
    assert not profile.passed
    assert [f.check for f in failed(profile)] and any(
        check == "merge_queue" for check, _ in failed(profile)
    )


def test_a_landing_branch_that_is_the_default_reports_no_divergence(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The common case says nothing about branches — a warning that always fires is noise."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub(default_branch="main")

    result = wired("init", "--wire", str(repo), script=answers(landing_branch="main"), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert "default branch" not in result.stdout


# -----------------------------------------------------------------------------
# The CI half: "when the repo has no CI producing those checks"
# -----------------------------------------------------------------------------


def test_existing_ci_already_producing_the_checks_is_left_alone(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The spec scaffolds a workflow only when the repo has no CI producing the checks."""
    existing = (
        "name: ci\non:\n  pull_request:\n  merge_group:\njobs:\n"
        "  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n"
        "  smoke:\n    name: smoke\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: make smoke\n"
    )
    repo = make_bare_repo(
        tmp_path,
        {"pyproject.toml": "[project]\nname='app'\n", ".github/workflows/ci.yml": existing},
    )
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / wiring.WORKFLOW_PATH).exists() is False
    assert (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8") == existing
    assert "ci.yml" in result.stdout

    # The gate<->check contract still holds: the queue requires the gate names,
    # and the repo's own CI already produces jobs by those names.
    assert onboarding_profile(repo, github).passed


def test_a_conflicting_managed_workflow_is_reported_never_clobbered(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """An operator's edits to the managed file are theirs; wiring reports, never overwrites."""
    hand_edited = "name: mine\non:\n  merge_group:\njobs:\n  other:\n    runs-on: ubuntu-latest\n"
    repo = make_bare_repo(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname='app'\n",
            str(wiring.WORKFLOW_PATH): hand_edited,
        },
    )
    github = FakeGitHub()

    result = wired("init", "--wire", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / wiring.WORKFLOW_PATH).read_text(encoding="utf-8") == hand_edited
    assert wiring.ATTENTION in result.stdout
    assert str(wiring.WORKFLOW_PATH) in result.stdout


# -----------------------------------------------------------------------------
# Without `--wire`, init is exactly what US1 landed
# -----------------------------------------------------------------------------


def test_plain_init_touches_no_github_and_offers_the_wiring(
    wired: Callable[..., Run], tmp_path: Path
) -> None:
    """The GitHub half is opt-in: `ergane init` alone issues no `gh` call at all."""
    repo = make_bare_repo(tmp_path, {"pyproject.toml": "[project]\nname='app'\n"})
    github = FakeGitHub()

    result = wired("init", str(repo), script=answers(), github=github)

    assert result.code == EXIT_OK, result.stderr
    assert github.calls == []
    assert (repo / wiring.WORKFLOW_PATH).exists() is False
    assert "--wire" in result.stdout


# -----------------------------------------------------------------------------
# The wiring surface itself: no direct call is made against a real repository
# -----------------------------------------------------------------------------


def test_no_wiring_call_can_reach_github_without_a_runner() -> None:
    """Structural: every `gh` invocation this component makes goes through `GhClient`.

    `factory/mergequeue/wiring.py` never spawns a process of its own — it holds
    no `subprocess`, no `gh` literal outside a printed remedy string, and reaches
    GitHub only through the client it is handed.
    """
    import inspect

    source = inspect.getsource(wiring)
    assert "subprocess" not in source
    assert "import os" not in source
